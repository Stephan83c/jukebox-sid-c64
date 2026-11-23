# SID Jukebox, client C64 v2.0 : tout en assembleur Kick Assembler 5.25 (Java). Sources dans src/, outils PC dans tools/.
#   make [SERVER=boombass.net] [PORT=6474]   client réseau (build/jukebox.prg)
#   make deploy [ULTIMATE=192.168.1.27]      envoie et lance sur l'Ultimate (UCI au repos, aucun téléchargement en cours)
#   make demo ; make vice                    démo sans réseau, un morceau intégré (tools/mktune.py ID d'abord) ; banc VICE
#   make release TAG=vX.Y                    zip de la release (jukebox-sid.prg + README.txt) joint par gh
KICKASS  ?= $(HOME)/KickAssembler/KickAss.jar
SERVER   ?= boombass.net
PORT     ?= 6474
VERSION  ?= 2.0
ULTIMATE ?= 192.168.1.27
PRG      := build/jukebox.prg
DEMO     := build/demo.prg
KICK      = java -jar $(KICKASS)

.PHONY: all demo clean deploy vice release FORCE
all: $(PRG)

build/options: FORCE
	@mkdir -p build; echo '$(SERVER) $(PORT) $(VERSION)' | cmp -s - $@ || echo '$(SERVER) $(PORT) $(VERSION)' > $@

$(PRG): $(wildcard src/*.asm src/*.inc) Makefile build/options
	@test -f $(KICKASS) || { echo "KickAss.jar introuvable : make KICKASS=/chemin/KickAss.jar"; exit 1; }
	$(KICK) src/main.asm -odir $(CURDIR)/build -o $(CURDIR)/$(PRG) -symbolfile :SERVER=$(SERVER) :PORT=$(PORT) :VERSION=$(VERSION)

demo: $(DEMO)
$(DEMO): $(wildcard src/*.asm) build/tune.inc Makefile
	$(KICK) src/demo.asm -odir $(CURDIR)/build -o $(CURDIR)/$(DEMO) -symbolfile :VERSION=$(VERSION)

# Règle UCI : ne pas redéployer pendant un téléchargement ni avec un socket ouvert.
deploy: $(PRG)
	curl -sS -X POST --data-binary @$(PRG) http://$(ULTIMATE)/v1/runners:run_prg

vice: $(DEMO)
	x64sc -autostart $(DEMO)

REPO ?= Stephan83c/jukebox-sid-c64
release: $(PRG)
	@test -n "$(TAG)" || { echo "usage: make release TAG=vX.Y"; exit 1; }
	cp $(PRG) build/jukebox-sid.prg
	rm -f build/jukebox-sid-$(TAG).zip
	zip -j build/jukebox-sid-$(TAG).zip build/jukebox-sid.prg README.txt
	gh release upload $(TAG) build/jukebox-sid-$(TAG).zip --clobber -R $(REPO)

clean:
	rm -rf build
