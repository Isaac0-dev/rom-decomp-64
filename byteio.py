from io import BytesIO
import struct

# Custom wrapper class for default BytesIO,
# designed to behave exactly like a file.


class CustomBytesIO(BytesIO):
    def __init__(self, data: bytes):
        self._data = data
        super().__init__(data)

    def read_u8(self):
        data = self.read(1)
        if len(data) < 1:
            raise EOFError("Not enough data to read u8")
        return data[0]

    def read_u16(self):
        data = self.read(2)
        if len(data) < 2:
            raise EOFError("Not enough data to read u16")
        return struct.unpack(">H", data)[0]

    def read_s16(self):
        data = self.read(2)
        if len(data) < 2:
            raise EOFError("Not enough data to read s16")
        return struct.unpack(">h", data)[0]

    def read_u32(self):
        data = self.read(4)
        if len(data) < 4:
            raise EOFError("Not enough data to read u32")
        return struct.unpack(">I", data)[0]

    def peek_u16(self):
        pos = self.tell()
        if pos + 2 > len(self._data):
            raise EOFError("Not enough data to peek u16")
        data = self._data[pos : pos + 2]
        return struct.unpack(">H", data)[0]

    # ---- Core Python behavior ----
    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        return self._data[key]

    # ---- Search operations ----
    def find(self, sub, start=None, end=None):
        return self._data.find(
            sub, 0 if start is None else start, len(self._data) if end is None else end
        )

    def rfind(self, sub, start=None, end=None):
        return self._data.rfind(
            sub, 0 if start is None else start, len(self._data) if end is None else end
        )

    def index(self, sub, start=None, end=None):
        return self._data.index(
            sub, 0 if start is None else start, len(self._data) if end is None else end
        )

    def rindex(self, sub, start=None, end=None):
        return self._data.rindex(
            sub, 0 if start is None else start, len(self._data) if end is None else end
        )

    def count(self, sub, start=None, end=None):
        return self._data.count(
            sub, 0 if start is None else start, len(self._data) if end is None else end
        )

    # ---- Prefix/suffix checks ----
    def startswith(self, prefix, start=None, end=None):
        return self._data.startswith(prefix, start, end)

    def endswith(self, suffix, start=None, end=None):
        return self._data.endswith(suffix, start, end)

    # ---- Splitting ----
    def split(self, sep=None, maxsplit=-1):
        return self._data.split(sep, maxsplit)

    def rsplit(self, sep=None, maxsplit=-1):
        return self._data.rsplit(sep, maxsplit)

    def partition(self, sep):
        return self._data.partition(sep)

    def rpartition(self, sep):
        return self._data.rpartition(sep)

    # ---- Conversion / formatting ----
    def hex(self, *args, **kwargs):
        return self._data.hex(*args, **kwargs)

    def decode(self, *args, **kwargs):
        return self._data.decode(*args, **kwargs)

    def tohex(self, *args, **kwargs):  # Py3.11+ alias
        return self._data.hex(*args, **kwargs)

    # ---- Block writes if immutability matters ----
    def write(self, *args, **kwargs):
        raise TypeError("CustomBytesIO is immutable; use a new object instead.")
