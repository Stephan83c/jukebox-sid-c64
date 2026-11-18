SERVEUR_IP ?= boombass.net
SERVEUR_PORT ?= 6474
ULTIMATE ?= 192.168.1.27
HISTART ?= 0xA700
MAX_SECS ?= 1000
VIS ?= 1

PRG := build/jukebox.prg
CFLAGS := -t c64 -O -C jukebox.cfg -Wl -D,__HISTART__=$(HISTART) \
  -DSERVEUR_IP='"$(SERVEUR_IP)"' -DSERVEUR_PORT=$(SERVEUR_PORT) -DMAX_SECS=$(MAX_SECS)

.PHONY: all deploy clean demo release
.DEFAULT_GOAL := all

# Version de démonstration : un morceau intégré, sans réseau (pour VICE) ; voir make_demo.py
demo: main.c uci.c play.s boot.s logo.s scroll.s stack.s demo.s demo.h jukebox.cfg
	@mkdir -p build
	cl65 -t c64 -O -C jukebox.cfg -Wl -D,__HISTART__=0x9800,-D,__LOADSIZE__=0x3800 -DDEMO -DVIS_DEFAULT=$(VIS) -DMAX_SECS=$(MAX_SECS) \
	  -DSERVEUR_IP='"$(SERVEUR_IP)"' -m build/demo.map -o build/demo.prg main.c uci.c play.s boot.s logo.s scroll.s stack.s demo.s
	@rm -f *.o; ls -l build/demo.prg
all: $(PRG)

build/options: FORCE
	@mkdir -p build; echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS)' | cmp -s - $@ || echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS)' > $@
FORCE:

$(PRG): build/options main.c uci.c uci.h ascii.h play.s boot.s logo.s scroll.s stack.s jukebox.cfg Makefile
	@mkdir -p build
	cl65 $(CFLAGS) -m build/jukebox.map -o $@ main.c uci.c play.s boot.s logo.s scroll.s stack.s
	@rm -f *.o
	@ls -l $@

# Aucun socket n'est ouvert pendant la lecture : on peut redéployer à tout moment.
deploy: $(PRG)
	curl -sS -X POST --data-binary @$(PRG) http://$(ULTIMATE)/v1/runners:run_prg

# Usage : make release TAG=v1.3  (compile avec les réglages par défaut et joint le .prg à la release GitHub)
REPO ?= Stephan83c/jukebox-sid-c64
release: $(PRG)
	@test -n "$(TAG)" || { echo "usage: make release TAG=vX.Y"; exit 1; }
	cp $(PRG) build/jukebox-sid.prg
	gh release upload $(TAG) build/jukebox-sid.prg --clobber -R $(REPO)

clean:
	rm -rf build *.o
