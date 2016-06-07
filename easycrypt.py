import sys
from Crypto.Cipher import AES

def encrypt(plain, key):
    if isinstance(plain, str):
        plain = plain.encode("utf-8")
    if len(plain) % 16:
        plain += b'\x00' * (16 - len(plain) % 16)
    aes = AES.new(key, AES.MODE_ECB)
    return aes.encrypt(plain)

def decrypt(scrambled, key):
    aes = AES.new(key, AES.MODE_ECB)
    return aes.decrypt(scrambled).decode("utf-8").rstrip("\0")


if __name__ == '__main__':
    with open(sys.argv[1], "rb") as f:
        dat = encrypt(f.read(), sys.argv[3])
    with open(sys.argv[2], "wb") as f:
        f.write(dat)
