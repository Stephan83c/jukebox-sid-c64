SERVEUR_IP ?= boombass.net
SERVEUR_PORT ?= 6474
ULTIMATE ?= 192.168.1.27
HISTART ?= 0xAF00
VERSION ?= 1.5
MAX_SECS ?= 1000
VIS ?= 1
# Oscar64 (https://github.com/drmortalwombat/oscar64) : chemin du compilateur, et de ses fichiers d'en-tête
# (par défaut le dossier include voisin du dossier bin). cc65 fournit ca65/ld65 pour la partie assembleur.
OSC ?= oscar64
export OSC OSCINC VERSION SERVEUR_IP SERVEUR_PORT MAX_SECS VIS HISTART

PRG := build/jukebox.prg
SRC := client.c main.c uci.c uci.h console.c play.s logo.s scroll.s asm.cfg build.sh Makefile

.PHONY: all deploy clean demo release
.DEFAULT_GOAL := all

# Version de démonstration : un morceau intégré, sans réseau (pour VICE) ; voir make_demo.py
demo: $(SRC) demo.s demo.h demo.bin
	./build.sh demo

all: $(PRG)

build/options: FORCE
	@mkdir -p build; echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS) $(VIS) $(VERSION)' | cmp -s - $@ || echo '$(SERVEUR_IP) $(SERVEUR_PORT) $(HISTART) $(MAX_SECS) $(VIS) $(VERSION)' > $@
FORCE:

$(PRG): build/options $(SRC)
	./build.sh

# Aucun socket n'est ouvert pendant la lecture : on peut redéployer à tout moment.
deploy: $(PRG)
	curl -sS -X POST --data-binary @$(PRG) http://$(ULTIMATE)/v1/runners:run_prg

# Usage : make release TAG=v1.3  (compile avec les réglages par défaut et joint le .prg à la release GitHub)
REPO ?= Stephan83c/jukebox-sid-c64
release: $(PRG)
	@test -n "$(TAG)" || { echo "usage: make release TAG=vX.Y"; exit 1; }
	cp $(PRG) build/jukebox-sid.prg
	rm -f build/jukebox-sid-$(TAG).zip
	zip -j build/jukebox-sid-$(TAG).zip build/jukebox-sid.prg README.txt
	gh release upload $(TAG) build/jukebox-sid-$(TAG).zip --clobber -R $(REPO)

clean:
	rm -rf build *.o
