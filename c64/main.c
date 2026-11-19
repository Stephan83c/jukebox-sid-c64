
#ifndef SERVEUR_IP
#define SERVEUR_IP "boombass.net"
#endif
#ifndef SERVEUR_PORT
#define SERVEUR_PORT 6474
#endif

#define BARRE 0x7C   /* '|' en ASCII : un littéral serait converti par cc65 */
#ifndef VIS_DEFAULT
#define VIS_DEFAULT 1
#endif
#ifndef MAX_SECS
#define MAX_SECS 1000   /* durée maximale d'un morceau (secondes) */
#endif
#define MEM_BAS  0x0800u   /* le morceau doit tenir entre ces deux adresses */
#define MEM_HAUT (RUN - 1u)   /* le client occupe RUN-$CFFF */


#ifdef DEMO
static const unsigned char demo_data[] = {
#embed "demo.bin"
};
static char d_title[] = DEMO_TITLE;
static char d_author[] = DEMO_AUTHOR;
static char d_released[] = DEMO_RELEASED;
static char d_scroll[] = "          SID JUKEBOX  ***  A SID RADIO FOR THE COMMODORE ULTIMATE  ***  CODED BY STEPHAN  ***  TUNES FROM THE HVSC  ***  HELLO CLAUDE, THANKS FOR THE HELP !          ";
#endif

static unsigned char chunk[128];
static char filtre[31];          /* recherche en cours (ASCII majuscule), vide = tout */
static unsigned char nfiltre;
static unsigned char aucun;      /* le serveur n'a rien trouvé pour ce filtre */
static char cmdr[48];
static char hdr[340];   /* en-tête OK|... : titre, auteur, année, texte du scroller (170 au plus) */

static unsigned t_id, t_size, t_secs, t_load, t_fps;
static char *t_title, *t_author, *t_released;

static unsigned jiffies_m(void)
{
    unsigned char b, h;
    do {
        b = *(volatile unsigned char *)0xA2;
        h = *(volatile unsigned char *)0xA1;
    } while (b != *(volatile unsigned char *)0xA2);
    return (h << 8) | b;
}

static void attendre(unsigned ticks)
{
    unsigned t = jiffies_m();
    while (jiffies_m() - t < ticks) {
    }
}

/* Texte reçu (ASCII) vers l'écran en majuscules/graphiques. */
static void montrer(const char *s, unsigned char max)
{
    unsigned char c;
    while ((c = *s++) != 0 && max--) {
        if (c >= 97 && c <= 122) {   /* minuscules ASCII */
            c -= 32;
        }
        if (c < 32 || c > 95) {
            c = '?';
        }
        cputc(c);
    }
}

static char *champ(char **p)
{
    char *debut = *p;
    char *q = debut;
    while (*q && *q != BARRE) {
        ++q;
    }
    if (*q) {
        *q++ = 0;
    }
    *p = q;
    return debut;
}

static unsigned nombre(const char *s)
{
    unsigned n = 0;
    while (*s >= '0' && *s <= '9') {
        n = n * 10 + (*s++ - '0');
    }
    return n;
}

/* Texte du scroller reçu (ASCII, dans l'en-tête) : converti SUR PLACE en indices de glyphes
   (make_scroll.py) : A-Z = 1-26, * . , ! ? - = 27-32, / ' : = 33-35, 0-9 = 36-45, le reste = espace (0) ; $FF à la fin.
   Le serveur fournit déjà les 10 espaces avant et après. */
static void charger_scroll(char *s)
{
    unsigned char n = 0, c, i;
    scr_ok = 0;
    while (s[n]) {
        c = s[n];
        if (c >= 97 && c <= 122) {
            c -= 32;
        }
        if (c >= 65 && c <= 90) {
            i = c - 64;
        } else {
            switch (c) {
            case 42: i = 27; break;   /* * */
            case 46: i = 28; break;   /* . */
            case 44: i = 29; break;   /* , */
            case 33: i = 30; break;   /* ! */
            case 63: i = 31; break;   /* ? */
            case 45: i = 32; break;   /* - */
            case 47: i = 33; break;   /* / */
            case 39: i = 34; break;   /* ' */
            case 58: i = 35; break;   /* : */
            default: i = (c >= 48 && c <= 57) ? c - 12 : 0;   /* 0-9 */
            }
        }
        s[n++] = i;
    }
    if (n) {
        s[n] = 0xFF;
        scr_ptr = (unsigned char *)s;
        scr_ok = 1;
    }
}

/* OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année|scroller */
static unsigned char analyser(void)
{
    char *p = hdr;
    if (hdr[0] != 'O' || hdr[1] != 'K' || hdr[2] != BARRE) {
        return 0;
    }
    p += 3;
    t_id = nombre(champ(&p));
    t_size = nombre(champ(&p));
    t_secs = nombre(champ(&p));
    t_fps = nombre(champ(&p));    /* cadence du morceau : 50 (PAL) ou 60 (NTSC) */
    song_nr = nombre(champ(&p));
    t_load = nombre(champ(&p));
    init_addr = nombre(champ(&p));
    play_addr = nombre(champ(&p));
    t_title = champ(&p);
    t_author = champ(&p);
    t_released = champ(&p);
    charger_scroll(champ(&p));
    /* ne jamais écrire hors de la zone libre */
    if (t_size == 0 || t_load < MEM_BAS || t_load > MEM_HAUT ||
        t_size > MEM_HAUT - t_load + 1u || song_nr == 0) {
        return 0;
    }
    return 1;
}

/* Demande un morceau et le copie à son adresse de chargement. 1 = ok. */
static unsigned char recuperer(void)
{
    int s, n;
    unsigned hn = 0, fait = 0, k, t0;
    unsigned char c, entete = 0, ok = 0, mort = 0;
    unsigned char *p;

#ifdef DEMO
    memcpy((unsigned char *)DEMO_LOAD, demo_data, DEMO_SIZE);
    t_load = DEMO_LOAD;
    init_addr = DEMO_INIT;
    play_addr = DEMO_PLAY;
    song_nr = 1;
    t_secs = DEMO_SECS;
    t_title = d_title;
    t_author = d_author;
    t_released = d_released;
    charger_scroll(d_scroll);
    return 1;
#endif
    s = net_ouvrir(SERVEUR_IP, SERVEUR_PORT);
    if (s < 0) {
        return 0;
    }
    memcpy(cmdr, "RANDOM", 6);
    k = 6;
    if (nfiltre) {
        cmdr[k++] = 32;
        memcpy(cmdr + k, filtre, nfiltre);
        k += nfiltre;
    }
    cmdr[k++] = LF;
    aucun = 0;
    if (net_ecrire(s, cmdr, k)) {
        t0 = jiffies_m();
        for (;;) {
            n = net_lire(s, (char *)chunk, 120);
            if (n < 0) {
                mort = 1;   /* socket libéré par l'Ultimate : ne plus y toucher */
                break;
            }
            if (n == 0) {
                if (jiffies_m() - t0 > 600) {
                    break;
                }
                continue;
            }
            t0 = jiffies_m();
            p = chunk;
            while (!entete && n) {
                c = *p++;
                --n;
                if (c == LF) {
                    hdr[hn] = 0;
                    if (hdr[0] == 'E') {
                        aucun = 1;   /* ERR|aucun morceau */
                    }
                    if (!analyser()) {
                        n = -2;   /* réponse refusée, mais le socket est vivant */
                        break;
                    }
                    entete = 1;
                } else if (hn < sizeof(hdr) - 1) {
                    hdr[hn++] = c;
                }
            }
            if (n < 0) {
                break;
            }
            if (entete && n) {
                k = t_size - fait;
                if ((unsigned)n < k) {
                    k = n;
                }
                memcpy((unsigned char *)t_load + fait, p, k);
                fait += k;
            }
            if (entete && fait >= t_size) {
                ok = 1;
                break;
            }
        }
        if (!mort) {
            net_ecrire(s, "QUIT\x0A", 5);
        }
    }
    if (!mort) {
        net_fermer(s);
    }
    return ok;
}

/* Demande le texte à chercher (auteur ou titre). RETURN seul = tout, RUN/STOP = annuler. */
static void saisir(void)
{
    unsigned char c, n = 0;
    char buf[sizeof(filtre)];

    while (*(volatile unsigned char *)0xCB != 64) {   /* attendre le relâchement de S */
    }
    *(volatile unsigned char *)0xC6 = 0;              /* vider le tampon clavier */
    memset((unsigned char *)(0x0400 + 13 * 40), 32, 8 * 40);   /* efface la zone d'effets */
    gotoxy(0, 14);
    textcolor(COLOR_LIGHTBLUE);
    cputs("SEARCH ARTIST OR TITLE:");
    gotoxy(0, 15);
    textcolor(COLOR_WHITE);
    cputs("> ");
    cursor(1);
    for (;;) {
        c = cgetc();
        if (c == 13) {
            memcpy(filtre, buf, n);
            filtre[n] = 0;
            nfiltre = n;
            break;
        }
        if (c == 3) {
            break;
        }
        if (c == 20 && n) {
            --n;
            gotoxy(2 + n, 15);
            cputc(32);
            gotoxy(2 + n, 15);
        } else if (c >= 32 && c <= 90 && n < sizeof(buf)) {
            buf[n++] = c;
            cputc(c);
        }
    }
    cursor(0);
}

static void deux(unsigned char n)
{
    unsigned char d = 0;
    while (n >= 10) {
        n -= 10;
        ++d;
    }
    cputc(48 + d);
    cputc(48 + n);
}

static void duree(unsigned t)
{
    unsigned char m = 0;
    while (t >= 60) {
        t -= 60;
        ++m;
    }
    deux(m);
    cputc(58);
    deux((unsigned char)t);
}

/* Longueur affichée d'un texte (au plus max). */
static unsigned char lg(const char *s, unsigned char max)
{
    unsigned char n = 0;
    while (s[n] && n < max) {
        ++n;
    }
    return n;
}

/* Début de ligne (texte aligné à gauche). */
static void debut(unsigned char row)
{
    gotoxy(0, row);
}

/* Ligne "ETIQUETTE: texte" centrée. */
static void champ_ligne(unsigned char row, const char *label, unsigned char couleur,
                        const char *txt, unsigned char max)
{
    unsigned char n = lg(txt, max);

    debut(row);
    textcolor(COLOR_LIGHTBLUE);
    cputs(label);
    textcolor(couleur);
    montrer(txt, n);
}

/* Message centré sur une ligne (efface la ligne d'abord). */
static void message(unsigned char row, const char *txt, unsigned char couleur)
{
    memset((unsigned char *)(0x0400 + row * 40), 32, 40);
    debut(row);
    textcolor(couleur);
    cputs(txt);
}

/* Ligne des touches : 40 colonnes pile (touche en blanc, action en gris, deux espaces entre les groupes). */
static void touche(const char *k, const char *action)
{
    textcolor(COLOR_WHITE);
    cputs(k);
    textcolor(COLOR_GRAY2);
    cputs(action);
}

static void options(void)
{
    gotoxy(0, 24);
    touche("SPC", "=NEXT  ");
    touche("S", "=FIND  ");
    touche("C", "=CLEAR  ");
    touche("V", "=VIS  ");
    touche("Q", "=QUI");
    /* dernière case de l'écran : écrite directement, sinon le curseur ferait défiler l'écran */
    *(unsigned char *)(0x0400 + 24 * 40 + 39) = 20;           /* T */
    *(unsigned char *)(0xD800 + 24 * 40 + 39) = COLOR_GRAY2;
}

/* Zone d'effets : trois barres fines serrées (voix 1 à 3, sans étiquette, lignes 14 à 16, colonnes 0 à 39), dégradé vert / jaune / rouge. */
static void zone_effets(void)
{
    unsigned char v, c, col;

    memset((unsigned char *)(0x0400 + 13 * 40), 32, 8 * 40);
    if (!vis_on) {
        return;
    }
    for (v = 0; v < 3; ++v) {
        for (c = 0; c < 40; ++c) {
            col = c < 22 ? COLOR_LIGHTGREEN : (c < 32 ? COLOR_YELLOW : COLOR_LIGHTRED);
            *(unsigned char *)(0xD800 + (14 + v) * 40 + c) = col;
        }
    }
}

static void ecran(void)
{
    *(volatile unsigned char *)0xD018 = 0x15;   /* jeu majuscules/graphiques (les textes sont en ASCII majuscule) */
    *(volatile unsigned char *)0x0291 = 0x80;   /* le KERNAL ne bascule plus avec C= + MAJ */
    clrscr();
    bordercolor(COLOR_BLACK);
    bgcolor(COLOR_BLACK);
    textcolor(COLOR_WHITE);
    debut(0);
    cputs("SID JUKEBOX V" VERSION);
    debut(1);
    textcolor(COLOR_LIGHTBLUE);
    cputs("SERVER ");
    cputs(SERVEUR_IP);
    textcolor(COLOR_WHITE);
}

void jukebox(void)
{
    unsigned char r;
    unsigned secs;

    vis_on = VIS_DEFAULT;

    ecran();
#ifndef DEMO
    if (!uci_present()) {
        message(4, "ENABLE COMMAND INTERFACE", COLOR_WHITE);
        for (;;) {
        }
    }
#endif
    for (;;) {
        message(3, "CONNECTING...", COLOR_WHITE);
        if (!recuperer()) {
            if (aucun) {
                message(3, "NO MATCH, PLAYING ANY...", COLOR_LIGHTRED);
                nfiltre = 0;
                attendre(120);
                continue;
            }
            message(3, uci_bloquee ? "ULTIMATE LOCKED: POWER CYCLE IT" : "FAILED, RETRYING...", COLOR_LIGHTRED);
            if (uci_bloquee) {
                for (;;) {
                }
            }
            attendre(180);
            continue;
        }
        ecran();
        champ_ligne(4, "TITLE: ", COLOR_YELLOW, t_title, 33);
        champ_ligne(5, "ARTIST: ", COLOR_WHITE, t_author, 32);
        champ_ligne(6, "RELEASED: ", COLOR_WHITE, t_released, 30);
        fps = t_fps == 60 ? 60 : 50;   /* cadence du morceau, pas celle de la machine */
        secs = t_secs > MAX_SECS ? MAX_SECS : t_secs;
        frames_max = secs * fps;
        debut(9);
        textcolor(COLOR_LIGHTBLUE);
        cputs("TIME: ");
        textcolor(COLOR_WHITE);
        cputs("00:00 / ");     /* le lecteur met à jour ces 5 chiffres (colonne 6, ligne 9) */
        duree(secs);
        if (nfiltre) {
            champ_ligne(10, "FILTER: ", COLOR_WHITE, filtre, nfiltre);
        } else {
            champ_ligne(10, "FILTER: ", COLOR_WHITE, "ALL", 3);
        }
        champ_ligne(11, "EFFECTS: ", COLOR_WHITE, vis_on ? "ON" : "OFF", 3);
        zone_effets();
        options();
        r = play_run();
        if (r == 2) {
            break;
        }
        if (r == 3) {
            saisir();
        } else if (r == 4) {
            nfiltre = 0;
        } else if (r == 5) {
            vis_on = !vis_on;   /* effets on/off : pris en compte au morceau suivant */
        }
    }
    clrscr();
    cputs("GOODBYE");
    ((void (*)(void))0xFCE2)();   /* reset à froid */
}
