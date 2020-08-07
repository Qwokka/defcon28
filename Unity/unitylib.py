import binascii
import socket
import struct
import random
import threading
import time

MSG_CONNECT = 0x01
MSG_PING    = 0x04

# I don't know why this value
START_REMOTE_SESS_ID = 0x45eb

UNKNOWN_CONSTANT_1 = 0x9840

class ByteWriter(object):
    def __init__(self):
        self._raw = b""

    def write_byte(self, x):
        self._raw += struct.pack(">B", x)

    def write_short(self, x):
        self._raw += struct.pack(">H", x)

    def write_int(self, x):
        self._raw += struct.pack(">L", x)

    def write_bytes(self, bytestr):
        for i in bytestr:
            self.write_byte(i)

    def bytes(self):
        return self._raw

class UnitySystemMessageWriter(object):
    def __init__(self, msg_type, seq, remote_session_id, local_session_id):
        self.msg_type = msg_type
        self.seq = seq
        self.remote_session_id = remote_session_id
        self.local_session_id = local_session_id

        self.body = ByteWriter()

    def bytes(self):
        header = ByteWriter()
        
        header.write_short(0x0000)          # Connection ID is always 0 for system packets
        header.write_byte(self.msg_type)
        header.write_short(self.seq)
        header.write_short(self.local_session_id)

        tail = ByteWriter()

        tail.write_short(self.remote_session_id)

        return header.bytes() + self.body.bytes() + tail.bytes()

class UnityUserMessageWriter(object):
    def __init__(self, host_id, seq, session_id):
        self.host_id = host_id
        self.seq = seq
        self.session_id = session_id

        self.body = ByteWriter()

    def bytes(self):
        header = ByteWriter()
        
        header.write_short(self.host_id)
        header.write_short(self.seq)
        header.write_short(self.session_id)

        return header.bytes() + self.body.bytes()
class UnityConnectMessageWriter(UnitySystemMessageWriter):
    def __init__(self, seq, remote_session_id, local_session_id, lib_version):
        super(UnityConnectMessageWriter, self).__init__(MSG_CONNECT, seq, remote_session_id, local_session_id)
        
        self.lib_version = lib_version

        self.body.write_short(0x0001)       # ?
        self.body.write_short(0x0000)       # ?
        self.body.write_int(self.lib_version)
        self.body.write_short(UNKNOWN_CONSTANT_1)   # ?

# Output must be 27 bytes long
class UnityPingMessageWriter(UnitySystemMessageWriter):
    def __init__(self,
                 host_id,
                 seq,
                 remote_session_id,
                 local_session_id,
                 send_time,
                 packet_drop_percent = 0x00,
                 packet_drop_rate = 0x00):
        super(UnityPingMessageWriter, self).__init__(MSG_PING, seq, remote_session_id, local_session_id)

        self.send_time = send_time
        self.packet_drop_percent = packet_drop_percent
        self.packet_drop_rate = packet_drop_rate

        self.body.write_short(0x0001)       # ?
        self.body.write_short(host_id)       # Index?
        self.body.write_short(0x0000)       # ?
        self.body.write_int(self.send_time) # Time 1(?)
        self.body.write_int(self.send_time) # Time 2(?)
        self.body.write_byte(self.packet_drop_percent)
        self.body.write_byte(self.packet_drop_rate)
        self.body.write_short(0x0000)       # ?

class UnityHighLevelMessageWriter(ByteWriter):
    def __init__(self, msg_type, msg_id, payload):
        self.msg_type = msg_type
        self.msg_id = msg_id
        self.payload = payload

        self._raw = b""
        
    def bytes(self):
        self.write_short(len(self.payload))              # Size
        self.write_short(swap_endian_short(self.msg_id))

        self.write_bytes(self.payload)

        return self._raw
    
class ByteReader(object):
    def __init__(self, raw):
        self._raw = raw

        self._byteindex = 0

    def read_byte(self):
        result = self._raw[self._byteindex]

        self._byteindex += 1

        return result

    def read_short(self):
        r1 = self.read_byte()
        r2 = self.read_byte()

        return r2 | r1 << 8

    def read_int(self):
        r1 = self.read_byte()
        r2 = self.read_byte()
        r3 = self.read_byte()
        r4 = self.read_byte()

        return r4 | (r3 << 8) | (r2 << 16) | (r1 << 24)

    def seek(self,  index):
        if index < 0 or index > self.total_bytes():
            raise Exception("Invalid seek index %s" % index)
        
        self._byteindex = index

    def tell(self):
        return self._byteindex

    def bytes_remaining(self):
        return len(self._raw) - self._byteindex

    def total_bytes(self):
        return len(self._raw)

class UnityMessageReader(ByteReader):
    def __init__(self, raw):
        self._raw = raw

        self._byteindex = 0

        self.host_id = self.read_short()
        self.msg_type = self.read_byte()
        self.seq_num = self.read_short()
        self.remote_session_id = self.read_short()

        self.local_session_id = self.read_local_session_id()

    def read_local_session_id(self):
        start_seek = self.tell()

        length = self.total_bytes()

        self.seek(length - 2)

        result = swap_endian_short(self.read_short())

        self.seek(start_seek)

        return result

class UnityPingMessageReader(UnityMessageReader):
    def __init__(self, raw):
        super(UnityPingMessageReader, self).__init__(raw)

        if len(raw) != 27:
            raise Exception("Got invalid length for ping packet (%s)" % len(raw))

        self.host_id = self.read_short()
        self.unknown_field_2 = self.read_short()
        self.unknown_field_3 = self.read_short()
        self.unknown_field_4 = self.read_int()
        self.unknown_field_5 = self.read_int()

class UnitySocket(object):
    def __init__(self,
                 ipaddr,
                 port,
                 host_id = 0x00,
                 seq_num = 0x3333,
                 session_id = 0x4444,
                 lib_version = 0x01000300,
                 debug = False):
        self.seq_num = seq_num
        self.session_id = session_id
        self.lib_version = lib_version
        self.debug = debug

        self.start_time = int(time.time() * 1000)

        self.host_id = host_id

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(1)

        self._sockinfo = (ipaddr, port)

    def send(self, msg_bytes):
        self._socket.sendto(msg_bytes, self._sockinfo)

    def recv_raw(self, size):
        data, addr = self._socket.recvfrom(size)

        return data

    def handle_packet(self):
        msg_raw = self.recv_raw(1024)

        if self.debug:
            print("< %s" % binascii.hexlify(msg_raw))

        msg_reader = UnityMessageReader(msg_raw)

        if msg_reader.host_id == 0:
            self.handle_system_message(msg_reader)
        else:
            self.handle_user_message(msg_reader)
            
    def handle_user_message(self, msg_reader):
        msg_writer = UnityUserMessageWriter(host_id = self.host_id,
                                            seq = self.seq_num,
                                            session_id = self.session_id)

        msg_writer.body.write_short(0x0000)
        msg_writer.body.write_short(0x0000)
        msg_writer.body.write_short(0x0000)
        
        msg_writer.body.write_byte(0x01)    # Channel ID

        payload = bytes([random.randrange(0, 0xFF)]) * random.randrange(1, 30)

        hl_msg = UnityHighLevelMessageWriter(msg_type = 0x01,
                                             msg_id = 0x05,
                                             payload = payload)

        hl_bytes = hl_msg.bytes()
        
        msg_writer.body.write_byte(len(hl_bytes))
        msg_writer.body.write_bytes(hl_bytes)
        
        msg_bytes = msg_writer.bytes()

        if self.debug:
            print("> %s" % binascii.hexlify(msg_bytes))

        self.send(msg_writer.bytes())

    def handle_system_message(self, msg_reader):
        if msg_reader.msg_type != MSG_PING:
            raise Exception("Got unhandled system message type %s" % msg_reader.msg_type)

        if msg_reader.msg_type == MSG_PING:
            msg_reader = UnityPingMessageReader(msg_reader._raw)

            self.send_ping_response(swap_endian_short(msg_reader.remote_session_id))

            if self.host_id == 0x00:
                self.host_id = msg_reader.host_id

                if self.debug:
                    print("GOT HOST ID %s" % self.host_id)
            
    def connect(self):
        msg = UnityConnectMessageWriter(seq = self.seq_num,
                                        remote_session_id = START_REMOTE_SESS_ID,
                                        local_session_id = self.session_id,
                                        lib_version = self.lib_version)

        msg_bytes = msg.bytes()

        self.send(msg_bytes)

        self.seq_num += 1
        
    def send_ping_response(self, remote_session_id):
        msg = UnityPingMessageWriter(seq = self.seq_num,
                                     host_id = self.host_id,
                                     remote_session_id = remote_session_id,
                                     local_session_id = self.session_id,
                                     send_time = self.time_elapsed())

        if self.debug:
            print("> %s" % binascii.hexlify(msg.bytes()))

        self.send(msg.bytes())

        self.seq_num += 1

    def time_elapsed(self):
        return (int(time.time() * 1000) - self.start_time)

    def inject_message(self, session_id, seq_num, body, channel_id = 0x01):
        msg_writer = UnityUserMessageWriter(host_id = self.host_id,
                                            seq = seq_num,
                                            session_id = session_id)

        msg_writer.body.write_bytes(body)

        msg_bytes = msg_writer.bytes()

        self.send(msg_writer.bytes())

def swap_endian_short(x):
    return x >> 8 | ((x & 0xff) << 8)
