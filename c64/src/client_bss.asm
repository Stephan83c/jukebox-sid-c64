// variables du client (BSS, entre la fin de son code et $BFFF)
uci_bloquee: .fill 1, 0     // une commande n'a pas abouti dans son délai : seule une coupure de courant relance l'Ultimate
rep_n:   .fill 1, 0
stat_n:  .fill 1, 0
un:      .fill 1, 0
us:      .fill 1, 0
ulim:    .fill 2, 0
tu:      .fill 2, 0
ta:      .fill 2, 0
tw:      .fill 2, 0
tr:      .fill 2, 0
wlim:    .fill 2, 0
rlim:    .fill 2, 0
cmd:     .fill 64, 0
rep:     .fill 128, 0
ustat:   .fill 17, 0
hdr:     .fill 300, 0       // en-tête OK3 ; le texte du scroller y est converti et lu par le lecteur pendant le morceau
filtre:  .fill 31, 0        // recherche en cours (ASCII majuscule), vide = tout
        .label SBUF = rep           // saisie de la recherche (pas de réseau pendant ce temps)
nbuf:    .fill 1, 0
nfiltre: .fill 1, 0
boucle:  .fill 1, 0         // 1 = on rejoue le même morceau à la fin
rejouer: .fill 1, 0         // 1 = on rejoue le morceau déjà en mémoire, sans le redemander
aucun:   .fill 1, 0         // le serveur n'a rien trouvé pour ce filtre
occupe:  .fill 1, 0         // ERR|trop de requetes
vieux:   .fill 1, 0         // serveur sans RANDOM3
perdu:   .fill 1, 0         // la recherche précédente n'a rien donné
mort:    .fill 1, 0
ok:      .fill 1, 0
sock:    .fill 1, 0
entete:  .fill 1, 0         // 0 = en-tête, 1 = morceau, 2 = bloc de relais
n:       .fill 1, 0
xs_:     .fill 1, 0
res:     .fill 1, 0
vis_on:  .fill 1, 0
secs:    .fill 2, 0
t_id:    .fill 2, 0
t_size:  .fill 2, 0
t_secs:  .fill 2, 0
t_fps:   .fill 2, 0
t_song:  .fill 2, 0
t_load:  .fill 2, 0
t_init:  .fill 2, 0
t_play:  .fill 2, 0
t_rz:    .fill 2, 0
t_rlen:  .fill 2, 0
t_complet: .fill 2, 0
t_end:   .fill 2, 0
r_end:   .fill 2, 0
t_title: .fill 2, 0
t_author: .fill 2, 0
t_released: .fill 2, 0
t_scroll: .fill 2, 0
numbuf:  .fill 6, 0         // id en décimal (GET3, message du garde-fou)
nb_i:    .fill 1, 0
