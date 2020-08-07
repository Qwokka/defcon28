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
import sys
import unitylib

usock = unitylib.UnitySocket(sys.argv[1], int(sys.argv[2]), host_id = 0x01)

seq_num = 0x1111

msg_body = b"ABCD"

# Session IDs cannot be even
for session_id in range(1, 0x10000, 2):
    usock.inject_message(session_id, seq_num, msg_body)
