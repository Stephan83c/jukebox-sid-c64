# SID Jukebox for the C64 Ultimate

[🇫🇷 Français](README.fr.md) · 🇬🇧 English

An online jukebox in the spirit of *Belote LAN C64*: the **C64 Ultimate** asks a server for a random SID tune,
receives it through the Ultimate's network interface (UCI/TCP) and **plays it itself** (the 6510 runs the
tune's own code, just like back in the day). No synchronisation between clients: everybody gets their own draw.

🌐 **Web page: <https://sidbox.boombass.net>**

The play screen: giant logo, title / artist / year, elapsed time, three VU meters (one per SID voice) in a
rainbow gradient, a demo-style scroller whose text comes from the server, and the key legend.

![Play screen (VICE emulation)](docs/screenshot.png)

*The play screen, captured in the VICE emulator (demo build): rainbow title, VU meters, server-driven scroller, version in the corner.*

```
 ┌────────────┐   text, TCP :6474     ┌──────────────────────┐
 │  server    │ ◄───────────────────► │  C64 Ultimate        │
 │ server.py  │   RANDOM3 [pattern]   │  c64/ (6502 assembly)│
 │ jukebox.db │ ──► OK3|…|code+relays │  UCI: TCP sockets    │
 └─────┬──────┘                       └──────────────────────┘
       │ indexer.py, sidscan (emulation)
 ┌─────┴──────┐
 │ HVSC (SID) │   ~61,000 files, lengths: Songlengths.md5
 └────────────┘
```

## Quick start

Requirements: Python 3, a C compiler (`cc`, for `sidscan`), `7z`, **Java** and **Kick Assembler** 5.25 (`make KICKASS=/path/KickAss.jar`, default `~/KickAssembler/KickAss.jar`), the C64 KERNAL and BASIC ROMs of VICE (for `sidscan`; `c64/chargen_set1.bin` only to regenerate the title, see `c64/tools/dump_chargen.py`), a C64 Ultimate with
the REST API and the *Command Interface* enabled. VICE is optional (hardware-free tests).

```sh
# 1. the HVSC (download from https://hvsc.c64.org/), then index the playable tunes
python3 indexer.py /path/to/C64Music -o jukebox.db --max-addr 0xAEFF
# 1b. the v2.0 analysis (emulates every tune, a few minutes): which tunes play, where they write to the SID
cc -O2 -o sidscan sidscan.c && python3 scan_db.py --root /path/to/C64Music

# 2. the server (port 6474)
python3 server.py --root /path/to/C64Music

# 3. the C64 client (SERVER, PORT and ULTIMATE on the command line or in c64/Makefile)
cd c64
make SERVER=boombass.net PORT=6474 ULTIMATE=192.168.1.27 deploy
```

`--max-addr` must stay equal to `HISTART - 1` (`c64/src/memmap.asm`), like `SCAN_HISTART` in `server.py` and the defaults of
`scan_db.py` and `update_db.sh`; `test_v3.py` checks it. It is the upper limit for tunes, the client lives in the memory above it.

## Running the server online

```sh
python3 server.py --root /path/to/C64Music --port 6474      # listens on 0.0.0.0 by default
```

- Open the TCP port in the firewall (`firewall-cmd --add-port=6474/tcp --permanent`) and at your host.
- Without root, a `systemd --user` service works (`~/.config/systemd/user/jukebox.service`,
  `Restart=on-failure`); for it to survive logout and reboot, an administrator must run
  `sudo loginctl enable-linger <account>`.
- Updating the tune database after a new HVSC release: [docs/UPDATE_DB.md](docs/UPDATE_DB.md).
- Publishing a new client version: [docs/RELEASE.md](docs/RELEASE.md).
- Updating from GitHub: `git pull` in the server folder (a read-only deploy key if the repo is private),
  then restart the server.

## Scroller text

The text comes from the file **`scroll.txt`** next to `server.py` (option `--scroll`). It is re-read on every
request: edit it without restarting, and the new text shows up **with the next tune** (the C64 does not talk to
the server while playing).

- Alphabet: `A-Z 0-9 * . , ! ? - / ' :` (45 glyphs); lower case is upper-cased, accents are stripped, anything else
  becomes a space.
- At most 150 characters; the server adds 10 spaces before and after.
- Missing or empty file: the C64 shows its short built-in text.

## Keys

| Key | Effect |
|---|---|
| `SPACE` | next tune |
| `S` | search by artist or title: the next tunes are picked at random among the matches (RETURN confirms, RUN/STOP cancels, empty RETURN = everything, i.e. clears the search; no match shows `NO MATCH` and any tune plays) |
| `L` | loop on/off: replays the same tune when it ends (the tune restarts when you toggle it; replayed from memory, no network) |
| `V` | VU meters on/off (restarts the same tune from 0:00) |
| `Q` | quit (back to BASIC) |

## The protocol (text, one command per line)

```
RANDOM [pattern]  ->  OK|id|size|seconds|frames/s|subtune|load|init|play|title|author|year|scroller\n
                      + <size> bytes of raw code (PSID header stripped)
RANDOM2 <end> [pattern]  ->  same, <end> = last address the client leaves to tunes (HISTART - 1), 4 hex digits,
                      e.g. AEFF: only tunes ending at or below it are offered (client v1.5+)
GET <id>          ->  same, for a specific tune
RANDOM3 <end> [pattern]  ->  OK3|id|size|seconds|frames/s|subtune|load|init|play|relays|relays_size|complete|title|author|year|scroller\n
                      + <size> bytes of code (SID write sites replaced by JSR to the relays) + <relays_size> bytes
                      of relay block, to copy at <relays> (client v2.0)
GET3 <id>         ->  same, for a specific tune
STATS             ->  STATS|compatible|total
error             ->  ERR|message
```

v1.x clients never get a modified tune, nor the tunes the analysis found harmful to their player (`v1_risque`, 683 tunes).
The full v2.0 specification is [SPEC-v2.md](SPEC-v2.md) (in French). Clients before v1.5 send plain `RANDOM`: the server then only offers tunes ending before `$A700`. A v1.5+ client talking to a server without `RANDOM2` (reply `ERR|commande inconnue`) falls back to plain `RANDOM`. The last field is the scroller text (see above). Debuggable with `nc`. The pattern is searched in artist or
title, case-insensitively.

## How it works

- **Sorting (`indexer.py`)**: reads each `.sid` header, finds the length through the file's MD5 in
  `Songlengths.md5`, and flags as `compatible` the tunes our player can run: PSID (not RSID), a single SID,
  frame-driven (not a CIA timer), play routine present, fits between `$0800` and `HISTART-1`, 16 KB at most.
  Rejections and their reason stay in the database.
- **Analysis (`sidscan.c`, `scan_db.py`, v2.0)**: a 6502 emulator plays each tune for 10,000 calls in the client's exact
  conditions; it rejects tunes that write into the client, hang or stay silent, and records every instruction that writes to
  the SID (table `scan`). The server replaces these instructions by `JSR` to small relays before sending the tune.
- **Player (`c64/src/player.asm`)**: one raster interrupt per frame drives the player. The tune's routine is called at the tune's own rate (50 or 60 Hz, sent by the server), whatever the machine's video mode: on a PAL or NTSC machine the tempo is the same (the machine's rate is measured when each tune starts; the pitch is corrected too: the SID clock differs by 3.8 %, so a tune of the other standard is scaled by about 0.96 or 1.04 in the frequency registers; the screen shows the machine and the tune rate after the time, e.g. `PAL  60HZ`). While playing, zero page
  belongs to the tune (saved before, restored after) and the keyboard is read straight from the matrix.
- **Exact sound and VU meters**: the SID registers are write-only. Each relay writes the value to the real SID and keeps a
  copy; the VU meters simulate each voice's ADSR envelope from it. (v1.x mapped RAM over the SID during the call and copied
  the registers once a frame: two writes to the same register in one frame were lost.)
- **Display**: play screen in VIC bank 3 (`$F400`, characters at `$F800`, RAM under the KERNAL), with a custom
  character set (thin VU bars, logo, scroller letters). The scroller uses hardware scrolling (`$D016`),
  confined to its two lines by two raster interrupts.
- **Memory map**: `$0800-(HISTART-1)` tune and relays; `HISTART-$BFFF` client (network, screens); `$C000-$CFFF` player
  (everything that runs around a tune call); `$D000-$DFFF` RAM saves; `$F400-$FFFF` display. `HISTART = $AF00`.

## Ultimate pitfalls (learned the hard way)

- **Never redeploy / reset the C64 with an open socket**: the Ultimate's command interface can hang until
  power is cycled. The client keeps no socket open while playing; to redeploy, wait for the "déconnexion"
  line in the server log.
- After a network read error (-1), do not write to or close that socket any more.
- Every network wait has a time limit (open 30 s, first line 10 s, data 5 s without a byte), counted on CIA 2, not on the IRQ.
- RAM under the KERNAL cannot be read back by the CPU (it sees the ROM): anything you need to re-read lives
  in an ordinary buffer.
- Changing a VIC-II colour mid-line leaves a grey pixel: if you do it, do it in the border.

## Files

| | |
|---|---|
| `indexer.py` | indexes the HVSC into `jukebox.db` (SQLite) |
| `update_db.sh` | re-index + upload + restart + test, with safeguards ([docs](docs/UPDATE_DB.md)) |
| `server.py` | asyncio server: draw, search, sends the code (with relays for v2.0) and the scroller text |
| `sidscan.c`, `scan_db.py` | v2.0 analysis by emulation, table `scan` |
| `test_v3.py` | checks the whole v2.0 chain against `sidscan` (whole base in a few minutes) |
| `bad_tunes.txt` | tunes removed by hand (`[v2]`: only for v1.x clients) |
| `scroll.txt` | scroller text, re-read on every tune |
| `client_pc.py` | PC test client; can also push a SID to the Ultimate through its REST API |
| `c64/src/main.asm`, `client.asm`, `net.asm` | client (Kick Assembler): loader, screens, search, network (UCI, time limits) |
| `c64/src/player.asm` | player: tune call, relays, VU meters, PAL/NTSC, watchdog, scroller, logo |
| `c64/src/memmap.asm` | memory map, `HISTART` |
| `c64/tools/mkbig.py`, `dump_chargen.py` | welcome-screen title; character ROM from VICE |
| `c64/tools/mktune.py`, `banc.py` | network-less demo build (`make demo`) and VICE test bench |
| `c64/tools/panne.py` | fault proxy between the C64 and the server (network failure tests) |
| `docs/v2.0/` | v2.0 development notes and hardware test results (in French) |

Updating the tune database: [docs/UPDATE_DB.md](docs/UPDATE_DB.md).
Project history (in French): [HISTORY.md](HISTORY.md).

## License and copyright

The code is released under the [GNU GPL v3](LICENSE) (for commits after v1.8; releases up to v1.8 stay MIT). The HVSC tunes are copyrighted; any use beyond private listening is subject to copyright (see the HVSC's
`DOCUMENTS/Disclaimer.txt`). This repository contains no tunes and no C64 ROM; running a public server was
discussed with the HVSC team, who replied on 2026-11-19: "It's all ok for us, please go on with your project." This is
the team's approval, not a licence: the rights stay with the original composers.
