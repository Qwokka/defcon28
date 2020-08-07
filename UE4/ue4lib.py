"""
Copyright (c) 2020 Jack Baker

This program is free software: you can redistribute it and/or modify  
it under the terms of the GNU General Public License as published by  
the Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful, but 
WITHOUT ANY WARRANTY; without even the implied warranty of 
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU 
General Public License for more details.

You should have received a copy of the GNU General Public License 
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
import socket
import struct
import sys

NAME_Actor      = 0x66
NAME_Control    = 0xff
NAME_Voice      = 0x100

NMT_Hello       = 0x00
NMT_Login       = 0x05
NMT_Join        = 0x09

class MessageWriter(object):
    def __init__(self, padded = True):
        self._buf = [0]

        self._bitindex = 0
        self._byteindex = 0

        self._padded = padded

    def get_bit_size(self):
        return (self._byteindex * 8) + self._bitindex

    def write_bit(self, bit):
        while (self._byteindex >= len(self._buf)):
            self._buf.append(0)

        this_byte = self._buf[self._byteindex]

        this_byte |= bit << self._bitindex

        self._buf[self._byteindex] = this_byte

        self._consume_bits(1)

    def write_byte(self, byte):
        for i in range(0, 8):
            self.write_bit((byte >> i) & 1)

    def write_buffer(self, byte_val, bit_length):
        byte_counter = 0
        bit_counter = 0

        for _ in range(0, bit_length):
            this_byte = byte_val[byte_counter]

            this_bit = (this_byte >> bit_counter) & 1

            self.write_bit(this_bit)

            bit_counter += 1

            if bit_counter > 7:
                byte_counter += 1
                bit_counter -= 8

    def write_int(self, int_val):
        int_str = struct.pack("<L", int_val)

        for i in range(0, 4):
            self.write_byte(int_str[i])

    def write_int_sized(self, int_val, bits):
        for i in range(0, bits):
            this_bit = int_val & (1 << i)

            if this_bit:
                self.write_bit(1)
            else:
                self.write_bit(0)

    def write_int_packed(self, int_val):
        current = int_val

        if not current:
            self.write_byte(0x00)
            return

        while current:
            this_byte = (current & 0x7f) << 1

            current >>= 7

            if current:
                this_byte |= 1

            self.write_byte(this_byte)

    def write_float(self, flt):
        float_str = struct.pack("<f", flt)

        for i in range(0, 4):
            self.write_byte(float_str[i])

    # Implementation of FArchive& operator<<( FArchive& Ar, FString& A )
    # NOTE: Does not support Unicode
    def write_fstring(self, str_val):
        str_val = str_val + "\x00"
        str_len = len(str_val)

        self.write_int_sized(str_len, 32)

        for i in range(0, str_len):
            self.write_byte(ord(str_val[i]))

    def _consume_bits(self, num):
        self._bitindex += num

        while self._bitindex > 7:
            self._bitindex -= 8
            self._byteindex += 1

    def output(self):
        if self._padded:
            if self._bitindex != 0:
                self.write_bit(1)

            while self._bitindex != 0:
                self.write_bit(0)

            if (self._buf[-1] == 0x00):
                self._buf.append(0x01)

        return bytes(self._buf)

class MessageReader(object):
    def __init__(self, data):
        self._buf = []

        for char in data:
            self._buf.append(char)

        self.done = False

        self._bitindex = 0
        self._byteindex = 0

        self._maxbits = len(data) * 8

    def bits_remaining(self):
        return self._maxbits - (self._bitindex + self._byteindex * 8)

    def read_bit(self):
        result_byte = self._buf[self._byteindex]

        result_bit = result_byte & (1 << self._bitindex)

        self._consume_bits(1)

        return result_bit != 0

    def read_uintx(self, count):
        result = 0

        for i in range(0, count):
            this_bit = self.read_bit()

            result |= this_bit << i

        return result

    def read_float(self):
        int_value = self.read_uintx(32)

        str_value = struct.pack("<L", int_value)

        float_value = struct.unpack("<f", str_value)[0]

        return float_value

    def read_string(self, bit_length):
        result = ""

        byte_counter = 0
        bit_counter = 0

        this_byte = 0

        for _ in range(0, bit_length):
            this_byte |= self.read_bit() << bit_counter

            bit_counter += 1

            if bit_counter > 7:
                byte_counter += 1
                bit_counter -= 8

                result += chr(this_byte)

                this_byte = 0

        return result

    def read_bits(self, bit_length):
        result = []

        byte_counter = 0
        bit_counter = 0

        this_byte = 0

        for _ in range(0, bit_length):
            this_byte |= self.read_bit() << bit_counter

            bit_counter += 1

            if bit_counter > 7:
                byte_counter += 1
                bit_counter -= 8

                result.append(this_byte)

                this_byte = 0

        return bytes(result)

    def _consume_bits(self, num):
        self._bitindex += num

        while self._bitindex > 7:
            self._bitindex -= 8
            self._byteindex += 1

        if (self._byteindex * 8) + self._bitindex >= self._maxbits:
            self.done = True

class UE4Socket(object):
    def __init__(self, ipaddr, port, net_version=0x4945cd76):
        self._ipaddr = ipaddr
        self._port = port
        self._net_version = net_version

        self._timestamp = None
        self._cookie = None

        self._opts = (self._ipaddr, self._port)

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._handshake()

    def send(self, msg):
        print(msg)
        self._socket.sendto(msg, self._opts)

    def recv(self, size):
        data, addr = self._socket.recvfrom(size)
        print(data)

        return data

    def _handshake(self):
        self._handshake_send_syn()
        self._handshake_recv_ack()
        self._handshake_send_synack()
        self._handshake_recv_ackack()

    def _handshake_send_syn(self):
        msg = MessageWriter()

        msg.write_bit(1)

        for _ in range(0, 191):
            msg.write_bit(0)

        msg.write_byte(0x08)

        self.send(msg.output())

    def _handshake_recv_ack(self):
        data = self.recv(1024)

        reader = MessageReader(data)

        handshake_packet = reader.read_bit()
        handshake_restart = reader.read_bit()
        self._active_secret = reader.read_bit()

        self._timestamp = reader.read_float()

        self._cookie = reader.read_bits(reader.bits_remaining())

        self._server_seq = struct.unpack("<H", self._cookie[:2])[0] & 0x3fff
        self._client_seq = struct.unpack("<H", self._cookie[2:4])[0] & 0x3fff

        self._in_reliable = self._client_seq & 1023

    def _handshake_send_synack(self):
        msg = MessageWriter()

        msg.write_bit(1)

        msg.write_bit(0)                        # Restart handshake
        msg.write_bit(self._active_secret)      # OutSecretId

        msg.write_float(self._timestamp)

        msg.write_buffer(self._cookie, 160)

        msg.write_bit(1)
        msg.write_bit(0)
        msg.write_bit(0)
        msg.write_bit(0)
        msg.write_bit(0)

        self.send(msg.output())

    def _handshake_recv_ackack(self):
        data = self.recv(1024)

        reader = MessageReader(data)

        handshake_packet = reader.read_bit()
        handshake_restart = reader.read_bit()
        self._active_secret = reader.read_bit()

        self._timestamp = reader.read_float()

    def handle_nmt_challenge(self):
        data = self.recv(1024)

        reader = MessageReader(data)

    def open_channel(self, ch_type):
        outermsg = MessageWriter(padded = True)

        outermsg.write_bit(0)

        msg = MessageWriter(padded = True)

        for _ in range(0, 4):
            msg.write_bit(0)

        seq_str = struct.pack("<H", self._client_seq)
        acked_seq_str = struct.pack("<H", self._server_seq - 1)

        msg.write_buffer(acked_seq_str, 14)
        msg.write_buffer(seq_str, 14)

        for _ in range(0, 32):
            msg.write_bit(0)

        msg.write_bit(0)                    # bHasServerFrameTime

        msg.write_byte(0x41)                # RemoteInKBytesPerSecondByte

        msg.write_bit(1)                    # bControl
        msg.write_bit(1)                    # bOpen
        msg.write_bit(0)                    # bClose
        msg.write_bit(0)                    # bIsReplicationPaused
        msg.write_bit(0)                    # bReliable

        msg.write_byte(0x00)                # ChIndex

        msg.write_bit(0)                    # bHasPackageMapExports
        msg.write_bit(0)                    # bHasMustBeMappedGUIDs
        msg.write_bit(1)                    # bPartial

        msg.write_bit(1)                    # bPartialInitial
        msg.write_bit(0)                    # bPartialFinal

        # UPackageMap::StaticSerializeName
        msg.write_bit(1)                    # bHardcoded

        msg.write_int_packed(ch_type)

        # BunchDataBits
        msg.write_int_sized(0, 13)

        output = msg.output()

        outermsg.write_buffer(output, len(output) * 8)

        self.send(outermsg.output())

    def nmt_hello(self):
        outermsg = MessageWriter(padded = True)

        outermsg.write_bit(0)

        msg = MessageWriter(padded = True)

        for _ in range(0, 4):
            msg.write_bit(0)

        seq_str = struct.pack("<H", self._client_seq)
        acked_seq_str = struct.pack("<H", (self._server_seq - 1) & 0xFFFF)

        msg.write_buffer(acked_seq_str, 14)
        msg.write_buffer(seq_str, 14)

        for _ in range(0, 32):
            msg.write_bit(0)

        msg.write_bit(0)                    # bHasServerFrameTime

        msg.write_byte(0x41)                # RemoteInKBytesPerSecondByte

        msg.write_bit(1)                    # bControl
        msg.write_bit(1)                    # bOpen
        msg.write_bit(0)                    # bClose
        msg.write_bit(0)                    # bIsReplicationPaused
        msg.write_bit(1)                    # bReliable

        msg.write_byte(0x00)                # ChIndex

        msg.write_bit(0)                    # bHasPackageMapExports
        msg.write_bit(0)                    # bHasMustBeMappedGUIDs
        msg.write_bit(0)                    # bPartial

        msg.write_int_sized(self._in_reliable + 1, 10)  # ChSequence

        # UPackageMap::StaticSerializeName
        msg.write_bit(1)                    # bHardcoded

        msg.write_int_packed(NAME_Control)  # NameIndex

        bunch = MessageWriter(padded = False)

        bunch.write_byte(NMT_Hello)                     # MessageType
        bunch.write_byte(0x01)                          # IsLittleEndian
        bunch.write_int_sized(self._net_version, 32)    # RemoteNetworkVersion (Windows)
        bunch.write_fstring("")                         # EncryptionToken

        bunch_size = bunch.get_bit_size()
        bunch_str = bunch.output()

        # BunchDataBits
        msg.write_int_sized(bunch_size, 13)
        msg.write_buffer(bunch_str, bunch_size)

        output = msg.output()

        outermsg.write_buffer(output, len(output) * 8)

        self.send(outermsg.output())

    def nmt_login(self, url = ""):
        outermsg = MessageWriter(padded = True)

        outermsg.write_bit(0)

        msg = MessageWriter(padded = True)

        for _ in range(0, 4):
            msg.write_bit(0)

        seq_str = struct.pack("<H", self._client_seq + 1)
        acked_seq_str = struct.pack("<H", (self._server_seq - 1) & 0xFFFF)

        msg.write_buffer(acked_seq_str, 14)
        msg.write_buffer(seq_str, 14)

        for _ in range(0, 32):
            msg.write_bit(0)

        msg.write_bit(0)                    # bHasServerFrameTime

        msg.write_byte(0x41)                # RemoteInKBytesPerSecondByte

        msg.write_bit(0)                    # bControl
        msg.write_bit(0)                    # bIsReplicationPaused
        msg.write_bit(1)                    # bReliable

        msg.write_byte(0x00)                # ChIndex

        msg.write_bit(0)                    # bHasPackageMapExports
        msg.write_bit(0)                    # bHasMustBeMappedGUIDs
        msg.write_bit(0)                    # bPartial

        msg.write_int_sized(self._in_reliable + 2, 10)          # ChSequence

        # UPackageMap::StaticSerializeName
        msg.write_bit(1)                    # bHardcoded

        msg.write_int_packed(NAME_Control)  # NameIndex

        bunch = MessageWriter(padded = False)

        bunch.write_byte(NMT_Login)         # MessageType
        bunch.write_fstring("")             # ClientResponse
        bunch.write_fstring(url)            # RequestURL

        # FArchive& operator<<(FArchive& Ar, FUniqueNetIdRepl& UniqueNetId)
        # (Runtime/Engine/Private/OnlineReplStructs.cpp)
        bunch.write_byte(0x00)              # EncodingFlags
        bunch.write_fstring("")             # Contents

        bunch.write_fstring("")             # OnlinePlatformName

        bunch_size = bunch.get_bit_size()
        bunch_str = bunch.output()

        # BunchDataBits
        msg.write_int_sized(bunch_size, 13)
        msg.write_buffer(bunch_str, bunch_size)

        output = msg.output()

        outermsg.write_buffer(output, len(output) * 8)

        self.send(outermsg.output())

    def send_net_guid_bunch(self, path):
        EXPORT_COUNT = 1
        EXPORT_SIZE = 0xb2

        outermsg = MessageWriter(padded = True)

        outermsg.write_bit(0)

        msg = MessageWriter(padded = True)

        for _ in range(0, 4):
            msg.write_bit(0)

        seq_str = struct.pack("<H", self._client_seq)
        acked_seq_str = struct.pack("<H", self._server_seq - 1)

        msg.write_buffer(acked_seq_str, 14)
        msg.write_buffer(seq_str, 14)

        for _ in range(0, 32):
            msg.write_bit(0)

        msg.write_bit(0)                    # bHasServerFrameTime

        msg.write_byte(0x41)                # RemoteInKBytesPerSecondByte

        msg.write_bit(1)                    # bControl
        msg.write_bit(1)                    # bOpen
        msg.write_bit(0)                    # bClose
        msg.write_bit(0)                    # bIsReplicationPaused
        msg.write_bit(0)                    # bReliable

        msg.write_byte(0x00)                # ChIndex

        msg.write_bit(1)                    # bHasPackageMapExports
        msg.write_bit(0)                    # bHasMustBeMappedGUIDs
        msg.write_bit(1)                    # bPartial

        msg.write_bit(1)                    # bPartialInitial
        msg.write_bit(0)                    # bPartialFinal

        # UPackageMap::StaticSerializeName
        msg.write_bit(1)                    # bHardcoded

        # NameIndex (0xFF = NAME_Control)
        msg.write_int_packed(0xff)

        bunch = MessageWriter(padded = False)

        # Inside UPackageMapClient::ReceiveNetGUIDBunch
        bunch.write_bit(0)                  # bHasRepLayoutExport

        bunch.write_int_sized(0x01, 32)     # NumGUIDsInBunch

        # Inside UPackageMapClient::InternalLoadObject
        bunch.write_int_packed(0x01)        # NetGUID

        bunch.write_byte(0x01)              # ExportFlags (bHasPath)

        # Second call to UPackageMapClient::InternalLoadObject
        bunch.write_int_packed(0x00)        # NetGUID

        bunch.write_fstring(path)

        bunch_size = bunch.get_bit_size()
        bunch_str = bunch.output()

        # BunchDataBits
        msg.write_int_sized(bunch_size, 13)
        msg.write_buffer(bunch_str, bunch_size)

        output = msg.output()

        outermsg.write_buffer(output, len(output) * 8)

        self.send(outermsg.output())

    def send_net_field_exports(self):
        EXPORT_COUNT = 1
        EXPORT_SIZE = 0xb2

        msg = MessageWriter()

        msg.write_bit(0)

        for _ in range(0, 4):
            msg.write_bit(0)

        seq_str = struct.pack("<H", self._client_seq)
        acked_seq_str = struct.pack("<H", self._server_seq - 1)

        msg.write_buffer(acked_seq_str, 14)
        msg.write_buffer(seq_str, 14)

        for _ in range(0, 32):
            msg.write_bit(0)

        msg.write_bit(0)                    # bHasServerFrameTime

        msg.write_byte(0x41)                # RemoteInKBytesPerSecondByte

        msg.write_bit(1)                    # bControl
        msg.write_bit(1)                    # bOpen
        msg.write_bit(0)                    # bClose
        msg.write_bit(0)                    # bIsReplicationPaused
        msg.write_bit(0)                    # bReliable

        msg.write_byte(0x00)                # ChIndex

        msg.write_bit(1)                    # bHasPackageMapExports
        msg.write_bit(0)                    # bHasMustBeMappedGUIDs
        msg.write_bit(1)                    # bPartial

        msg.write_bit(1)                    # bPartialInitial
        msg.write_bit(0)                    # bPartialFinal

        # UPackageMap::StaticSerializeName
        msg.write_bit(1)                    # bHardcoded

        # NameIndex (0xFF = NAME_Control)
        msg.write_int_packed(0xff)

        # BunchDataBits
        msg.write_int_sized(33 + (EXPORT_COUNT * EXPORT_SIZE), 13)

        # Bunch Data
        msg.write_bit(1)                    # bHasRepLayoutExport
        msg.write_int(EXPORT_COUNT)         # NumLayoutCmdExports

        for i in range(0, EXPORT_COUNT):
            msg.write_int_packed(0x00)      # PathNameIndex

            msg.write_bit(1)                # Is path exported(?)

            # PathName
            msg.write_int(0x00000002)       # SaveNum
            msg.write_byte(0x5a)
            msg.write_byte(0x00)
            msg.write_int(0x00000041)       # MaxExports

            # NetFieldExport
            msg.write_byte(0x01)            # Flags

            # Handle
            msg.write_int_packed(0x80000000)

            # CompatibleChecksum
            msg.write_int(0x41414141)

            # ExportName
            msg.write_bit(1)                # bHardcoded
            msg.write_int_packed(0x33)      # NameIndex

        output = msg.output()

        self.send(output)
