#!/usr/bin/env python3
import argparse
import struct
import sys

RD_GPUADDR = 3
RD_CMDSTREAM_ADDR = 6
RD_BUFFER_CONTENTS = 12
RD_CHIP_ID = 14


def section(out, kind, payload):
    out.write(struct.pack("<II", kind, len(payload)))
    out.write(payload)


def buffer(out, addr, data):
    section(out, RD_GPUADDR, struct.pack("<III", addr & 0xffffffff, len(data), addr >> 32))
    section(out, RD_BUFFER_CONTENTS, data)


def main():
    p = argparse.ArgumentParser(
        description="Wrap raw Adreno command-stream dumps into a .rd file for cffdump")
    p.add_argument("-c", "--chip", type=lambda s: int(s, 16), default=0x03000520,
                   help="chip id in hex (default 03000520 = Adreno 305B on minnow)")
    p.add_argument("-a", "--addr", type=lambda s: int(s, 0), default=0x10000000,
                   help="GPU address of the command stream (default 0x10000000)")
    p.add_argument("-b", "--buf", action="append", default=[],
                   help="extra buffer referenced by the stream, ADDR:FILE (repeatable)")
    p.add_argument("cmdstream", help="raw little-endian dword dump of the ring/IB")
    p.add_argument("output", help="output .rd file")
    a = p.parse_args()

    with open(a.cmdstream, "rb") as f:
        cmds = f.read()
    if len(cmds) % 4:
        sys.exit("command stream size is not a multiple of 4")

    with open(a.output, "wb") as out:
        section(out, RD_CHIP_ID, struct.pack("<Q", a.chip))
        for spec in a.buf:
            addr, path = spec.split(":", 1)
            with open(path, "rb") as f:
                buffer(out, int(addr, 0), f.read())
        buffer(out, a.addr, cmds)
        section(out, RD_CMDSTREAM_ADDR,
                struct.pack("<III", a.addr & 0xffffffff, len(cmds) // 4, a.addr >> 32))


if __name__ == "__main__":
    main()
