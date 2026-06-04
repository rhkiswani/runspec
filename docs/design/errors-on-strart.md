(windows-utilities) finestoj@LONWL048262:Projects$ runspec-console
ERROR: Exception (client): Error reading SSH protocol banner'utf-8' codec can't decode byte 0x8b in position 9: invalid start byte
ERROR: Exception (client): Error reading SSH protocol banner'utf-8' codec can't decode byte 0xb9 in position 7: invalid start byte
ERROR: Traceback (most recent call last):
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2213, in _check_banner
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2213, in _check_banner
ERROR:     buf = self.packetizer.readline(timeout)
ERROR:     buf = self.packetizer.readline(timeout)
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 401, in readline
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 401, in readline
ERROR:     return u(buf)
ERROR:     return u(buf)
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\util.py", line 332, in u
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\util.py", line 332, in u
ERROR:     return s.decode(encoding)
ERROR:     return s.decode(encoding)
ERROR:            ~~~~~~~~^^^^^^^^^^
ERROR:            ~~~~~~~~^^^^^^^^^^
ERROR: UnicodeDecodeError: 'utf-8' codec can't decode byte 0x8b in position 9: invalid start byte
ERROR: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb9 in position 7: invalid start byte
ERROR:
ERROR:
ERROR: During handling of the above exception, another exception occurred:
ERROR: During handling of the above exception, another exception occurred:
ERROR:
ERROR:
ERROR: Traceback (most recent call last):
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2029, in run
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2029, in run
ERROR:     self._check_banner()
ERROR:     self._check_banner()
ERROR:     ~~~~~~~~~~~~~~~~~~^^
ERROR:     ~~~~~~~~~~~~~~~~~~^^
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2217, in _check_banner
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2217, in _check_banner
ERROR:     raise SSHException(
ERROR:     raise SSHException(
ERROR:         "Error reading SSH protocol banner" + str(e)
ERROR:         "Error reading SSH protocol banner" + str(e)
ERROR:     )
ERROR:     )
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner'utf-8' codec can't decode byte 0x8b in position 9: invalid start byte
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner'utf-8' codec can't decode byte 0xb9 in position 7: invalid start byte
ERROR:
ERROR:
ERROR: Exception (client): Error reading SSH protocol banner
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2213, in _check_banner
ERROR:     buf = self.packetizer.readline(timeout)
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 395, in readline
ERROR:     buf += self._read_timeout(timeout)
ERROR:            ~~~~~~~~~~~~~~~~~~^^^^^^^^^
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 673, in _read_timeout
ERROR:     raise socket.timeout()
ERROR: TimeoutError
ERROR:
ERROR: During handling of the above exception, another exception occurred:
ERROR:
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2029, in run
ERROR:     self._check_banner()
ERROR:     ~~~~~~~~~~~~~~~~~~^^
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2217, in _check_banner
ERROR:     raise SSHException(
ERROR:         "Error reading SSH protocol banner" + str(e)
ERROR:     )
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
ERROR:
ERROR: Exception (client): Error reading SSH protocol banner
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2213, in _check_banner
ERROR:     buf = self.packetizer.readline(timeout)
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 395, in readline
ERROR:     buf += self._read_timeout(timeout)
ERROR:            ~~~~~~~~~~~~~~~~~~^^^^^^^^^
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\packet.py", line 673, in _read_timeout
ERROR:     raise socket.timeout()
ERROR: TimeoutError
ERROR:
ERROR: During handling of the above exception, another exception occurred:
ERROR:
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2029, in run
ERROR:     self._check_banner()
ERROR:     ~~~~~~~~~~~~~~~~~~^^
ERROR:   File "C:\Users\finestoj\Projects\windows-utilities\Lib\site-packages\paramiko\transport.py", line 2217, in _check_banner
ERROR:     raise SSHException(
ERROR:         "Error reading SSH protocol banner" + str(e)
ERROR:     )
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
ERROR:
