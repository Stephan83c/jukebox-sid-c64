SERVEUR_IP ?= 192.168.1.55
SERVEUR_PORT ?= 6464
ULTIMATE ?= 192.168.1.27
HISTART ?= 0xA900
MAX_SECS ?= 1000
VIS ?= 1

PRG := build/jukebox.prg
CFLAGS := -t c64 -O -C jukebox.cfg -Wl -D,__HISTART__=$(HISTART) \
  -DSERVEUR_IP='"$(SERVEUR_IP)"' -DSERVEUR_PORT=$(SERVEUR_PORT) -DMAX_SECS=$(MAX_SECS)

.PHONY: all deploy clean demo
.DEFAULT_GOAL := all

# Version de démonstration : un morceau intégré, sans réseau (pour VICE) ; voir make_demo.py
demo: main.c uci.c play.s boot.s logo.s scroll.s demo.s demo.h jukebox.cfg
	@mkdir -p build
	cl65 -t c64 -O -C jukebox.cfg -Wl -D,__HISTART__=0x9800,-D,__LOADSIZE__=0x3800 -DDEMO -DVIS_DEFAULT=$(VIS) -DMAX_SECS=$(MAX_SECS) \
	  -DSERVEUR_IP='"$(SERVEUR_IP)"' -m build/demo.map -o build/demo.prg main.c uci.c play.s boot.s logo.s scroll.s demo.s
	@rm -f *.o; ls -l build/demo.prg
all: $(PRG)

build/options: FORCE
	@mkdir -p build; echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS)' | cmp -s - $@ || echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS)' > $@
FORCE:

$(PRG): build/options main.c uci.c uci.h ascii.h play.s boot.s logo.s scroll.s jukebox.cfg Makefile
	@mkdir -p build
	cl65 $(CFLAGS) -m build/jukebox.map -o $@ main.c uci.c play.s boot.s logo.s scroll.s
	@rm -f *.o
	@ls -l $@

# Aucun socket n'est ouvert pendant la lecture : on peut redéployer à tout moment.
deploy: $(PRG)
	curl -sS -X POST --data-binary @$(PRG) http://$(ULTIMATE)/v1/runners:run_prg

clean:
	rm -rf build *.o
