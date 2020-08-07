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
import ue4lib

exp_sock = ue4lib.UE4Socket(sys.argv[1], int(sys.argv[2]))

exp_sock.nmt_hello()
exp_sock.nmt_login("\\\\asdf.umap.com\\hi\\hi.txt")
