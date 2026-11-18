# Updating the tune database (`jukebox.db`)

[🇫🇷 Français](UPDATE_DB.fr.md) · 🇬🇧 English

The database is rebuilt from scratch by `indexer.py` from a newer HVSC (the script deletes the old output
file). Tune ids change every time; that does not matter, the C64 always asks for a random tune.

## Shortcut: `update_db.sh`

```sh
./update_db.sh /path/to/C64Music                # re-index, upload, restart, test
./update_db.sh /path/to/C64Music --local-only   # re-index only (nothing is uploaded)
```

It does steps 2 to 4 below, with safeguards: the database is built into a fresh file and only adopted if it
keeps at least 90 % of the old one's tunes (backup `jukebox.db.bak`); it waits until no C64 is connected
before restarting (`--force` to override); it asks for confirmation before uploading (`--yes` to skip) and
tests the server at the end. Settings through environment variables (`SERVER`, `SSH_PORT`, `REMOTE_DIR`,
`PORT`, `MAX_ADDR`…), see the script header. The manual steps remain valid.

## 1. Get the new HVSC

Full release from <https://hvsc.c64.org/> (the current database comes from #85). Replacing the whole
`C64Music` folder is safer than applying the update archives. `DOCUMENTS/Songlengths.md5` is part of the
archive: the indexer uses it for tune lengths.

## 2. Re-index (on your PC)

```sh
cp jukebox.db jukebox.db.bak                      # safety net
python3 indexer.py /path/to/C64Music -o jukebox.db --max-addr 0xA8FF
```

`--max-addr` must stay equal to `HISTART - 1` (`c64/Makefile`) and to `MEM_HAUT` (`c64/main.c`): above it is
the C64 client's memory. The script prints how many tunes were kept and why the others were rejected (RSID,
too big, multi-SID, CIA-timer driven…). With HVSC #85: about 44,555 playable tunes.

## 3. Upload to the server

`C64Music/` and `jukebox.db` are not in git: copy them by hand. The two must match (the database holds
paths into `C64Music`).

```sh
rsync -az --delete -e "ssh -p 22" /path/to/C64Music <account>@<server>:jukebox/
rsync -az -e "ssh -p 22" jukebox.db <account>@<server>:jukebox/
```

`--delete` removes files from the server that are no longer in the new HVSC.

## 4. Restart the server

It keeps the database open, so a restart is required.

```sh
systemctl --user restart jukebox
```

A connection lasts about a second per tune; still, check the log (`journalctl --user -u jukebox -n 5`) that
no C64 is connected. Then test:

```sh
python3 client_pc.py --host <server> --port 6474
```

## If the C64 client changes size

A bigger client sits higher in memory: lower `HISTART` (`c64/Makefile`), `MEM_HAUT` (`c64/main.c`) and
`--max-addr` together, then re-index; the catalogue loses a few tunes (see the table in `HISTORY.md`).

## Copyright

The HVSC is for private use (`DOCUMENTS/Disclaimer.txt`); running a public server is still to be settled with
the HVSC team or the composers.
