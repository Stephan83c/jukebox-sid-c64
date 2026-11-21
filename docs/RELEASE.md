# Publishing a new client version

Follow these steps in this order. Run the `make` commands in `c64/`.

1. **Version**: change it everywhere *before* building: `c64/Makefile` (`VERSION`), `c64/build.sh` (default value),
   the title of `c64/README.txt`, and a new entry at the top of `HISTORY.md`.
2. **Scroller**: `scroll.txt` and `d_scroll` in `c64/main.c` (`Vx.y IS AVAILABLE`), keeping the text the same
   length: the client is full.
3. **Documentation**: if a key or a behaviour changes, update `c64/README.txt`, `README.md` and `README.fr.md`
   (the table of keys).
4. **Build**: `make OSC=~/oscar64/bin/oscar64`, then check the version:
   `strings build/jukebox.prg | grep "JUKEBOX V"`.
5. **Deploy to the C64 Ultimate**: `make deploy`, only *after* step 1, otherwise the screen shows the old version.
   Check the version in the top right corner of the play screen.
6. **Commit, tag, push**: `git commit`, `git tag vX.Y`, `git push origin main vX.Y`, once everything is ready. Do not
   move the tag afterwards.
7. **GitHub release**: run `gh release create vX.Y` (notes in French and English) *first*, then
   `make release TAG=vX.Y`, which attaches the zip. Check with `cmp` that the zip's `jukebox-sid.prg` is identical to
   `c64/build/jukebox.prg`, the one that was deployed.
8. **Public server**: `git pull`. The server's `scroll.txt` may differ from the repository's: check it before
   overwriting it. A moved tag is only picked up with `git fetch --tags --force`.
9. **Issues**: comment with the link to the release, and close the ones that are fixed.
