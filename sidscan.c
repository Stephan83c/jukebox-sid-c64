/* SID Jukebox v2.0 : analyse des morceaux par émulation 6502 (sidscan), voir SPEC-v2.md §4 et §5.
 * Copyright (C) 2026 Stephan83c
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Joue chaque morceau dans les conditions du client v2.0 : init puis N appels de play, chacun entré avec $01 = $36
 * (E/S visibles : le morceau écrit au vrai SID), drapeau I mis, $02A6 = norme du morceau (1 = PAL, 0 = NTSC).
 * Relève les écritures, lectures et exécutions, les écritures SID (adresse et opcode de l'instruction), les cycles.
 * Rend le verdict (§4.2), la liste des relais et la zone du bloc de relais (§5.2, §5.3).
 *
 * Usage : sidscan [histart_hex] [appels] [--dump DOSSIER] < liste      (lignes « id|chemin|sous-morceau|images/s »)
 *   --dump : pour chaque morceau relayé, écrit DOSSIER/id.code (octets chargement..fin, sites remplacés) et DOSSIER/id.relay
 *   (bloc de relais), fabriqués par la même fonction que la 2e émulation : référence des tests du serveur (étape 2).
 * Sortie, une ligne par morceau :
 *   id|sous-morceau|verdict|raison|complet|relay_addr(hex)|relay_len|nsites|nrelais|init_cycles|play_max|port_init|port_play|lit_02a6|verif|relais|autres|v1_risque
 *   v1_risque (décision D9, §6.2 : morceaux à ne plus envoyer aux clients v1.x), somme de : 1 = écrit $028F/$0290 (KEYLOG),
 *   2 = écrit dans $0314-$0333 (vecteurs du KERNAL), 4 = laisse $01 avec la ROM BASIC visible après init ou play
 *   verif (2e émulation avec les relais en place) : ok, diff (autre suite d'écritures SID), plante, copie (copie fausse), - (non faite)
 *   verdict = ok ou ko ; relais = « adresse:opcode » dans l'ordre des relais ; autres = « adresse:opcode:raison » (sites non relayés :
 *   mode, copie = code recopié hors des octets envoyés, miroir, smc = octets réécrits, data = octets relus, saut = saut au milieu, trop).
 * ROM : ~/.local/share/vice/C64/kernal-901227-03.bin et basic-901226-01.bin.
 * Compiler : cc -O2 -o sidscan sidscan.c   (cœur 6502 repris de sidcheck.c, que sidscan remplace)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCAN_VERSION 2          /* à changer à chaque modification de l'outil ou de la carte mémoire du client (§4.3) */
#define PAL_CPS 985248ULL       /* cycles par seconde (PAL) */
#define LINE_CYC 63ULL
#define LINES 312ULL
#define INIT_MAX (2ULL * PAL_CPS)          /* scan_initlong : 2 s */
#define PLAY_CAP 200000ULL                 /* appel de play abandonné au-delà (bien au-dessus des seuils) */
#define PLAY_MAX50 15000ULL                /* scan_playlong (§4.2) */
#define PLAY_MAX60 7000ULL                 /* morceau 60 Hz : deux appels possibles dans une image PAL (§7.6) */
#define RELAY_COST 17ULL                   /* JSR + RTS + écriture dans la copie, par écriture SID relayée */
#define SILENT_CALLS 300
#define MAX_RELAYS 48
#define MAX_SITES 1024

static unsigned char ram[65536], kernal[8192], basic[8192];
static unsigned char a, x, y, s, p, port;
static unsigned short pc;
static unsigned long long cycles;
static unsigned lo = 0xAF00;
static int fl_client, fl_save, fl_badexec, fl_jam, fl_brk;
static unsigned first_bad;
static int rd02a6, infetch, v1r;
static unsigned long sidw_call, sidw_total;
static unsigned long long sidhash;      /* empreinte de la suite des écritures SID (registre, valeur) */
static unsigned char lastreg[32];
static int verif;                       /* 2e passage (morceau modifié) : on ne relève plus les sites */

/* état de chaque adresse pendant l'émulation du morceau en cours */
#define A_W 1    /* écrite */
#define A_R 2    /* lue comme donnée */
#define A_X 4    /* début d'instruction exécutée */
#define A_F 8    /* lue comme opérande d'instruction */
static unsigned char acc[65536];

struct site { unsigned short ad; unsigned char op; unsigned long n; unsigned short eamin, eamax; };
static struct site sites[MAX_SITES];
static int nsites, sites_over;
static unsigned short ipc;
static unsigned char iop;

#define FC 0x01
#define FZ 0x02
#define FI 0x04
#define FD 0x08
#define FB 0x10
#define FV 0x40
#define FN 0x80

/* cycles de base de chaque opcode (sans franchissement de page ; +1 pour un branchement pris) */
static const unsigned char cyc[256] = {
 7,6,0,8,3,3,5,5,3,2,2,2,4,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7,
 6,6,0,8,3,3,5,5,4,2,2,2,4,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7,
 6,6,0,8,3,3,5,5,3,2,2,2,3,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7,
 6,6,0,8,3,3,5,5,4,2,2,2,5,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7,
 2,6,2,6,3,3,3,3,2,2,2,2,4,4,4,4, 2,6,0,6,4,4,4,4,2,5,2,5,5,5,5,5,
 2,6,2,6,3,3,3,3,2,2,2,2,4,4,4,4, 2,5,0,5,4,4,4,4,2,4,2,4,4,4,4,4,
 2,6,2,8,3,3,5,5,2,2,2,2,4,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7,
 2,6,2,8,3,3,5,5,2,2,2,2,4,4,6,6, 2,5,0,8,4,4,6,6,2,4,2,7,4,4,7,7 };

static int io_vis(void) { return (port & 3) != 0 && (port & 4); }
static int kernal_vis(void) { return (port & 2) != 0; }
static int basic_vis(void) { return (port & 3) == 3; }

static void bad(unsigned ad, int *f) { if (!first_bad) first_bad = ad; *f = 1; }

static unsigned char rd(unsigned short ad)
{
    if (infetch) acc[ad] |= A_F;
    if (ad >= 0xA000 && ad < 0xC000 && basic_vis()) return basic[ad - 0xA000];
    if (ad >= 0xE000 && kernal_vis()) return kernal[ad - 0xE000];
    if (ad >= 0xD000 && ad < 0xE000 && io_vis()) {
        unsigned line = (unsigned)((cycles / LINE_CYC) % LINES);
        switch (ad) {
        case 0xD011: return (unsigned char)(0x1B | ((line & 0x100) ? 0x80 : 0));
        case 0xD012: return (unsigned char)line;
        case 0xD41B: return (unsigned char)(cycles * 7);
        case 0xD41C: return (unsigned char)(cycles >> 6);
        case 0xDC04: case 0xDD04: return (unsigned char)(~cycles);
        case 0xDC05: case 0xDD05: return (unsigned char)(~cycles >> 8);
        default: return 0;
        }
    }
    if (ad == 1) return port;
    if (!infetch) {
        acc[ad] |= A_R;
        if (ad == 0x02A6) rd02a6 = 1;
    }
    return ram[ad];
}

static void sid_write(unsigned short ad, unsigned char v)
{
    int i;
    sidw_call++;
    sidw_total++;
    sidhash = (sidhash ^ (unsigned long long)(((ad & 0x1F) << 8) | v)) * 1099511628211ULL;
    lastreg[ad & 0x1F] = v;
    if (verif) return;
    for (i = 0; i < nsites; i++)
        if (sites[i].ad == ipc) break;
    if (i == nsites) {
        if (nsites == MAX_SITES) { sites_over = 1; return; }
        sites[i].ad = ipc; sites[i].op = iop; sites[i].n = 0; sites[i].eamin = 0xFFFF; sites[i].eamax = 0;
        nsites++;
    }
    sites[i].n++;
    if (ad < sites[i].eamin) sites[i].eamin = ad;
    if (ad > sites[i].eamax) sites[i].eamax = ad;
}

static void wr(unsigned short ad, unsigned char v)
{
    if (ad == 1) { port = v; return; }
    if (ad >= 0xD000 && ad < 0xE000 && io_vis()) {      /* va aux E/S, pas en RAM */
        if (ad >= 0xD400 && ad < 0xD800) sid_write(ad, v);
        return;
    }
    acc[ad] |= A_W;
    if (ad == 0x028F || ad == 0x0290) v1r |= 1;
    else if (ad >= 0x0314 && ad <= 0x0333) v1r |= 2;
    if (ad >= lo && ad < 0xD000) bad(ad, &fl_client);
    else if ((ad >= 0xD100 && ad < 0xD400) || (ad >= 0xD800 && ad < 0xDC00) || ad >= 0xFFFA) bad(ad, &fl_save);
    ram[ad] = v;
}

static void push(unsigned char v) { acc[0x100 + s] |= A_W; ram[0x100 + s--] = v; }
static unsigned char pull(void) { return ram[0x100 + ++s]; }
static void nz(unsigned char v) { p = (unsigned char)((p & ~(FN | FZ)) | (v & FN) | (v ? 0 : FZ)); }

static void adc(unsigned char v)
{
    unsigned c = p & FC;
    if (p & FD) {
        unsigned l = (a & 15) + (v & 15) + c, h;
        if (l > 9) l += 6;
        h = (a >> 4) + (v >> 4) + (l > 15);
        p &= ~(FN | FV | FZ | FC);
        if (!((a + v + c) & 0xFF)) p |= FZ;
        if (h & 8) p |= FN;
        if (~(a ^ v) & (a ^ (h << 4)) & 0x80) p |= FV;
        if (h > 9) h += 6;
        if (h > 15) p |= FC;
        a = (unsigned char)((h << 4) | (l & 15));
    } else {
        unsigned r = a + v + c;
        p &= ~(FV | FC);
        if (~(a ^ v) & (a ^ r) & 0x80) p |= FV;
        if (r > 255) p |= FC;
        a = (unsigned char)r;
        nz(a);
    }
}

static void sbc(unsigned char v)
{
    unsigned c = p & FC, r = a - v - (1 - c);
    unsigned char old = a;
    p &= ~(FV | FC);
    if ((a ^ v) & (a ^ r) & 0x80) p |= FV;
    if (r < 256) p |= FC;
    nz((unsigned char)r);
    if (p & FD) {
        int l = (old & 15) - (v & 15) - (1 - (int)c), h;
        h = (old >> 4) - (v >> 4) - (l < 0);
        if (l < 0) l -= 6;
        if (h < 0) h -= 6;
        a = (unsigned char)((h << 4) | (l & 15));
    } else {
        a = (unsigned char)r;
    }
}

static void cmp(unsigned char r, unsigned char v)
{
    p = (unsigned char)((p & ~FC) | (r >= v ? FC : 0));
    nz((unsigned char)(r - v));
}

static unsigned char asl_(unsigned char v) { p = (unsigned char)((p & ~FC) | (v >> 7)); v <<= 1; nz(v); return v; }
static unsigned char lsr_(unsigned char v) { p = (unsigned char)((p & ~FC) | (v & 1)); v >>= 1; nz(v); return v; }
static unsigned char rol_(unsigned char v) { unsigned char c = p & FC; p = (unsigned char)((p & ~FC) | (v >> 7)); v = (unsigned char)((v << 1) | c); nz(v); return v; }
static unsigned char ror_(unsigned char v) { unsigned char c = p & FC; p = (unsigned char)((p & ~FC) | (v & 1)); v = (unsigned char)((v >> 1) | (c << 7)); nz(v); return v; }

static unsigned short rw(unsigned short ad) { return (unsigned short)(rd(ad) | (rd((unsigned short)(ad + 1)) << 8)); }

static const unsigned char mode[256] = {
 0,8,0,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6,
 5,8,0,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6,
 0,8,0,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6,
 0,8,0,8,2,2,2,2,0,1,0,1,11,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6,
 1,8,1,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,4,4,0,7,0,7,6,6,7,7,
 1,8,1,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,4,4,0,7,0,7,6,6,7,7,
 1,8,1,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6,
 1,8,1,8,2,2,2,2,0,1,0,1,5,5,5,5, 10,9,0,9,3,3,3,3,0,7,0,7,6,6,6,6 };

static int step(void)
{
    unsigned char op, v, m;
    unsigned short ea = 0, base;
    /* exécution autorisée : RAM sous HISTART, ROM visibles ; interdite : le client, les E/S, la RAM sous E/S et KERNAL */
    if (pc >= lo && pc < 0xD000) { bad(pc, &fl_client); return 0; }
    if (pc >= 0xD000 && pc < 0xE000) { bad(pc, &fl_badexec); return 0; }
    if (pc >= 0xE000 && !kernal_vis()) { bad(pc, &fl_badexec); return 0; }
    acc[pc] |= A_X;
    ipc = pc;
    infetch = 1;
    op = rd(pc); iop = op; m = mode[op];
    pc++;
    cycles += cyc[op];
    switch (m) {
    case 1: ea = pc++; break;
    case 2: ea = rd(pc++); break;
    case 3: ea = (unsigned char)(rd(pc++) + x); break;
    case 4: ea = (unsigned char)(rd(pc++) + y); break;
    case 5: ea = rw(pc); pc += 2; break;
    case 6: ea = (unsigned short)(rw(pc) + x); pc += 2; break;
    case 7: ea = (unsigned short)(rw(pc) + y); pc += 2; break;
    case 8: base = (unsigned char)(rd(pc++) + x); ea = (unsigned short)(ram[base] | (ram[(unsigned char)(base + 1)] << 8)); break;
    case 9: base = rd(pc++); ea = (unsigned short)((ram[base] | (ram[(unsigned char)(base + 1)] << 8)) + y); break;
    case 10: ea = (unsigned short)(pc + 1 + (signed char)rd(pc)); pc++; break;
    case 11: base = rw(pc); pc += 2; ea = (unsigned short)(rd(base) | (rd((unsigned short)((base & 0xFF00) | ((base + 1) & 0xFF))) << 8)); break;
    }
    infetch = 0;
    if (m == 1) acc[ea] |= A_F;      /* l'immédiat est un opérande, pas une donnée */
#define BR(c) if (c) { pc = ea; cycles++; } break
    switch (op) {
    /* chargements, rangements */
    case 0xA9: case 0xA5: case 0xB5: case 0xAD: case 0xBD: case 0xB9: case 0xA1: case 0xB1: a = rd(ea); nz(a); break;
    case 0xA2: case 0xA6: case 0xB6: case 0xAE: case 0xBE: x = rd(ea); nz(x); break;
    case 0xA0: case 0xA4: case 0xB4: case 0xAC: case 0xBC: y = rd(ea); nz(y); break;
    case 0x85: case 0x95: case 0x8D: case 0x9D: case 0x99: case 0x81: case 0x91: wr(ea, a); break;
    case 0x86: case 0x96: case 0x8E: wr(ea, x); break;
    case 0x84: case 0x94: case 0x8C: wr(ea, y); break;
    case 0xAA: x = a; nz(x); break; case 0xA8: y = a; nz(y); break;
    case 0x8A: a = x; nz(a); break; case 0x98: a = y; nz(a); break;
    case 0xBA: x = s; nz(x); break; case 0x9A: s = x; break;
    /* logique, arithmétique */
    case 0x29: case 0x25: case 0x35: case 0x2D: case 0x3D: case 0x39: case 0x21: case 0x31: a &= rd(ea); nz(a); break;
    case 0x09: case 0x05: case 0x15: case 0x0D: case 0x1D: case 0x19: case 0x01: case 0x11: a |= rd(ea); nz(a); break;
    case 0x49: case 0x45: case 0x55: case 0x4D: case 0x5D: case 0x59: case 0x41: case 0x51: a ^= rd(ea); nz(a); break;
    case 0x69: case 0x65: case 0x75: case 0x6D: case 0x7D: case 0x79: case 0x61: case 0x71: adc(rd(ea)); break;
    case 0xE9: case 0xEB: case 0xE5: case 0xF5: case 0xED: case 0xFD: case 0xF9: case 0xE1: case 0xF1: sbc(rd(ea)); break;
    case 0xC9: case 0xC5: case 0xD5: case 0xCD: case 0xDD: case 0xD9: case 0xC1: case 0xD1: cmp(a, rd(ea)); break;
    case 0xE0: case 0xE4: case 0xEC: cmp(x, rd(ea)); break;
    case 0xC0: case 0xC4: case 0xCC: cmp(y, rd(ea)); break;
    case 0x24: case 0x2C: v = rd(ea); p = (unsigned char)((p & ~(FN | FV | FZ)) | (v & (FN | FV)) | ((a & v) ? 0 : FZ)); break;
    /* décalages, incréments mémoire */
    case 0x0A: a = asl_(a); break; case 0x4A: a = lsr_(a); break; case 0x2A: a = rol_(a); break; case 0x6A: a = ror_(a); break;
    case 0x06: case 0x16: case 0x0E: case 0x1E: wr(ea, asl_(rd(ea))); break;
    case 0x46: case 0x56: case 0x4E: case 0x5E: wr(ea, lsr_(rd(ea))); break;
    case 0x26: case 0x36: case 0x2E: case 0x3E: wr(ea, rol_(rd(ea))); break;
    case 0x66: case 0x76: case 0x6E: case 0x7E: wr(ea, ror_(rd(ea))); break;
    case 0xE6: case 0xF6: case 0xEE: case 0xFE: v = (unsigned char)(rd(ea) + 1); nz(v); wr(ea, v); break;
    case 0xC6: case 0xD6: case 0xCE: case 0xDE: v = (unsigned char)(rd(ea) - 1); nz(v); wr(ea, v); break;
    case 0xE8: x++; nz(x); break; case 0xC8: y++; nz(y); break;
    case 0xCA: x--; nz(x); break; case 0x88: y--; nz(y); break;
    /* sauts, pile, drapeaux */
    case 0x10: BR(!(p & FN)); case 0x30: BR(p & FN); case 0x50: BR(!(p & FV)); case 0x70: BR(p & FV);
    case 0x90: BR(!(p & FC)); case 0xB0: BR(p & FC); case 0xD0: BR(!(p & FZ)); case 0xF0: BR(p & FZ);
    case 0x4C: case 0x6C: pc = ea; break;
    case 0x20: pc--; push((unsigned char)(pc >> 8)); push((unsigned char)pc); pc = ea; break;
    case 0x60: pc = (unsigned short)(pull() | (pull() << 8)); pc++; break;
    case 0x40: p = pull(); pc = (unsigned short)(pull() | (pull() << 8)); break;
    case 0x48: push(a); break; case 0x68: a = pull(); nz(a); break;
    case 0x08: push(p | FB | 0x20); break; case 0x28: p = pull(); break;
    case 0x18: p &= ~FC; break; case 0x38: p |= FC; break; case 0x58: p &= ~FI; break; case 0x78: p |= FI; break;
    case 0xD8: p &= ~FD; break; case 0xF8: p |= FD; break; case 0xB8: p &= ~FV; break;
    case 0xEA: break;
    case 0x00: fl_brk = 1; return 0;
    /* opcodes illégaux courants */
    case 0xA7: case 0xB7: case 0xAF: case 0xBF: case 0xA3: case 0xB3: case 0xAB: a = x = rd(ea); nz(a); break;   /* LAX */
    case 0x87: case 0x97: case 0x8F: case 0x83: wr(ea, a & x); break;                                          /* SAX */
    case 0xC7: case 0xD7: case 0xCF: case 0xDF: case 0xDB: case 0xC3: case 0xD3: v = (unsigned char)(rd(ea) - 1); wr(ea, v); cmp(a, v); break; /* DCP */
    case 0xE7: case 0xF7: case 0xEF: case 0xFF: case 0xFB: case 0xE3: case 0xF3: v = (unsigned char)(rd(ea) + 1); wr(ea, v); sbc(v); break;   /* ISC */
    case 0x07: case 0x17: case 0x0F: case 0x1F: case 0x1B: case 0x03: case 0x13: v = asl_(rd(ea)); wr(ea, v); a |= v; nz(a); break;          /* SLO */
    case 0x27: case 0x37: case 0x2F: case 0x3F: case 0x3B: case 0x23: case 0x33: v = rol_(rd(ea)); wr(ea, v); a &= v; nz(a); break;          /* RLA */
    case 0x47: case 0x57: case 0x4F: case 0x5F: case 0x5B: case 0x43: case 0x53: v = lsr_(rd(ea)); wr(ea, v); a ^= v; nz(a); break;          /* SRE */
    case 0x67: case 0x77: case 0x6F: case 0x7F: case 0x7B: case 0x63: case 0x73: v = ror_(rd(ea)); wr(ea, v); adc(v); break;                 /* RRA */
    case 0x0B: case 0x2B: a &= rd(ea); nz(a); p = (unsigned char)((p & ~FC) | (a >> 7)); break;                                              /* ANC */
    case 0x4B: a &= rd(ea); a = lsr_(a); break;                                                                                             /* ALR */
    case 0x6B: a &= rd(ea); a = ror_(a); break;                                                                                             /* ARR (approché) */
    case 0xCB: { unsigned r = (unsigned)(a & x) - rd(ea); x = (unsigned char)r; p = (unsigned char)((p & ~FC) | (r < 256 ? FC : 0)); nz(x); break; } /* SBX */
    case 0x9F: case 0x93: wr(ea, (unsigned char)(a & x & ((ea >> 8) + 1))); break;                                                           /* SHA */
    case 0x9E: wr(ea, (unsigned char)(x & ((ea >> 8) + 1))); break;                                                                         /* SHX */
    case 0x9C: wr(ea, (unsigned char)(y & ((ea >> 8) + 1))); break;                                                                         /* SHY */
    case 0x9B: s = a & x; wr(ea, (unsigned char)(s & ((ea >> 8) + 1))); break;                                                               /* TAS */
    case 0xBB: a = x = s = rd(ea) & s; nz(a); break;                                                                                        /* LAS */
    case 0x8B: a = x & rd(ea); nz(a); break;                                                                                                /* ANE (approché) */
    case 0x1A: case 0x3A: case 0x5A: case 0x7A: case 0xDA: case 0xFA:
    case 0x80: case 0x82: case 0x89: case 0xC2: case 0xE2:
    case 0x04: case 0x44: case 0x64: case 0x14: case 0x34: case 0x54: case 0x74: case 0xD4: case 0xF4:
    case 0x0C: case 0x1C: case 0x3C: case 0x5C: case 0x7C: case 0xDC: case 0xFC: break;                                                     /* NOP */
    default: fl_jam = 1; return 0;
    }
    return 1;
}

/* Appelle une routine comme le client v2 : $01 = $36, I mis, retour par RTS vers $FFF0. 0 = trop long. */
static int call(unsigned short ad, unsigned char ac, unsigned long long max)
{
    unsigned long long fin = cycles + max;
    port = 0x36;
    p |= FI;
    s = 0xF0;
    push(0xFF); push(0xEF);
    pc = ad; a = ac; x = 0; y = 0;
    while (pc != 0xFFF0) {
        if (!step()) return 1;
        if (cycles > fin) return 0;
    }
    return 1;
}

static int sitecmp(const void *u, const void *v)
{
    const struct site *s1 = u, *s2 = v;
    return s1->n < s2->n ? 1 : s1->n > s2->n ? -1 : (int)s1->ad - (int)s2->ad;
}

/* raison pour laquelle un site n'est pas remplaçable (§5.2), ou 0 */
static unsigned cur_load, cur_end;

static const char *non_remplacable(const struct site *t)
{
    unsigned short b = (unsigned short)(ram[(unsigned short)(t->ad + 1)] | (ram[(unsigned short)(t->ad + 2)] << 8));
    int k;
    if (!(t->op == 0x8D || t->op == 0x8E || t->op == 0x8C || t->op == 0x9D || t->op == 0x99)) return "mode";
    if (t->ad < cur_load || t->ad + 2u > cur_end) return "copie";   /* code recopié ailleurs : absent des octets envoyés */
    if (b < 0xD400 || b > 0xD41F || t->eamin < 0xD400 || t->eamax > 0xD41F) return "miroir";
    for (k = 0; k < 3; k++) {
        unsigned short q = (unsigned short)(t->ad + k);
        if (acc[q] & A_W) return "smc";
        if (acc[q] & A_R) return "data";
        if (k && (acc[q] & A_X)) return "saut";
    }
    return 0;
}

static int libre(unsigned debut, unsigned n, unsigned load, unsigned end)
{
    unsigned i;
    if (debut < 0x0800 || debut + n > lo) return 0;
    if (debut <= end && debut + n > load) return 0;
    for (i = debut; i < debut + n; i++)
        if (acc[i]) return 0;
    return 1;
}

/* zone du bloc de relais (§5.3) : après la fin, avant le chargement, sinon le premier trou */
static unsigned zone(unsigned n, unsigned load, unsigned end)
{
    unsigned d;
    if (libre(end + 1, n, load, end)) return end + 1;
    if (load >= n && libre(load - n, n, load, end)) return load - n;
    for (d = 0x0800; d + n <= lo; d++)
        if (libre(d, n, load, end)) return d;
    return 0;
}

struct passage { int ok_init, ok_play; unsigned long long init_cyc, play_max, hash; unsigned long sid_early, sidw; unsigned port_init, port_play; int v1; };

/* Fabrication du morceau modifié (§5.4), identique à celle du serveur : la copie (32 octets en rz) reste telle quelle
 * (à zéro), les relais suivent, chaque site devient JSR vers son relais. Utilisée par emuler() et par --dump. */
static void fabriquer(unsigned char *m, const struct site *rel, unsigned nrel, unsigned rz)
{
    unsigned k;
    for (k = 0; k < nrel; k++) {
        unsigned short ad = rel[k].ad, st = (unsigned short)(rz + 32 + 7 * k);
        unsigned short base = (unsigned short)(m[(unsigned short)(ad + 1)] | (m[(unsigned short)(ad + 2)] << 8));
        unsigned short cp = (unsigned short)(rz + (base & 0x1F));
        m[st] = rel[k].op; m[st + 1] = (unsigned char)base; m[st + 2] = (unsigned char)(base >> 8);
        m[st + 3] = rel[k].op; m[st + 4] = (unsigned char)cp; m[st + 5] = (unsigned char)(cp >> 8);
        m[st + 6] = 0x60;
        m[ad] = 0x20; m[ad + 1] = (unsigned char)st; m[ad + 2] = (unsigned char)(st >> 8);
    }
}

/* Une émulation complète (init + appels de play). patch : sites remplacés par JSR vers le bloc de relais en rz (§5.1). */
static struct passage emuler(const unsigned char *buf, unsigned n, unsigned off, unsigned load, unsigned init, unsigned play,
                             unsigned song, unsigned fps, unsigned calls, const struct site *rel, unsigned nrel, unsigned rz)
{
    struct passage r;
    unsigned i;
    unsigned long long t0, d;
    memset(&r, 0, sizeof r);
    r.ok_play = 1;
    r.port_play = 0x36;
    memset(ram, 0, sizeof ram);
    memset(acc, 0, sizeof acc);
    memset(lastreg, 0, sizeof lastreg);
    for (i = lo; i < 0xD000; i++) ram[i] = 0xEA;
    if (off < n) memcpy(ram + load, buf + off, (n - off) > 65536 - load ? 65536 - load : n - off);
    fabriquer(ram, rel, nrel, rz);
    ram[0x02A6] = fps == 60 ? 0 : 1;
    fl_client = fl_save = fl_badexec = fl_jam = fl_brk = 0;
    first_bad = 0; rd02a6 = 0; v1r = 0; sidw_total = 0; sidhash = 14695981039346656037ULL;
    if (!verif) { nsites = 0; sites_over = 0; }
    cycles = 0; p = FI; a = x = y = 0;

    t0 = cycles;
    r.ok_init = call((unsigned short)init, (unsigned char)(song - 1), INIT_MAX);
    r.init_cyc = cycles - t0;
    r.port_init = port;
    if ((port & 3) == 3) v1r |= 4;
    r.sid_early = sidw_total;
    if (r.ok_init && !fl_jam && !fl_brk && !fl_badexec && !fl_client && play)
        for (i = 0; i < calls && r.ok_play && !fl_jam && !fl_brk && !fl_badexec && !fl_client; i++) {
            sidw_call = 0;
            t0 = cycles;
            r.ok_play = call((unsigned short)play, 0, PLAY_CAP);
            d = cycles - t0 + (verif ? 0 : RELAY_COST * sidw_call);
            if (d > r.play_max) r.play_max = d;
            if (port != 0x36) r.port_play = port;
            if ((port & 3) == 3) v1r |= 4;
            if (i + 1 == SILENT_CALLS) r.sid_early = sidw_total;
            cycles += 19656 - (cycles - t0) % 19656;   /* l'image suivante : le raster avance comme sur la machine */
        }
    if (calls < SILENT_CALLS) r.sid_early = sidw_total;
    r.hash = sidhash;
    r.v1 = v1r;
    r.sidw = sidw_total;
    return r;
}

int main(int argc, char **argv)
{
    FILE *f;
    char line[1024];
    unsigned calls = argc > 2 ? (unsigned)atoi(argv[2]) : 10000;
    const char *home = getenv("HOME");
    char path[512];
    static unsigned char buf[70000];
    if (argc > 1) lo = (unsigned)strtoul(argv[1], 0, 16);
    const char *dump = argc > 4 && !strcmp(argv[3], "--dump") ? argv[4] : 0;
    if (argc > 1 && !strcmp(argv[1], "--version")) { printf("%d\n", SCAN_VERSION); return 0; }
    snprintf(path, sizeof path, "%s/.local/share/vice/C64/kernal-901227-03.bin", home);
    if (!(f = fopen(path, "rb")) || fread(kernal, 1, 8192, f) != 8192) { fprintf(stderr, "ROM KERNAL introuvable\n"); return 1; }
    fclose(f);
    snprintf(path, sizeof path, "%s/.local/share/vice/C64/basic-901226-01.bin", home);
    if (!(f = fopen(path, "rb")) || fread(basic, 1, 8192, f) != 8192) { fprintf(stderr, "ROM BASIC introuvable\n"); return 1; }
    fclose(f);

    while (fgets(line, sizeof line, stdin)) {
        char *id = strtok(line, "|\n"), *fn = strtok(0, "|\n"), *sg = strtok(0, "|\n"), *fp = strtok(0, "|\n");
        unsigned n, off, load, init, play, end, song, fps, i, k, nrel = 0, rz = 0, rlen = 0;
        int complet;
        struct passage r1, r2;
        const char *raison = "", *ver = "-";
        static struct site rel[MAX_SITES];
        static char autres[16384], relais[8192];
        if (!id || !fn) continue;
        song = sg ? (unsigned)atoi(sg) : 1;
        fps = fp ? (unsigned)atoi(fp) : 50;
        if (!(f = fopen(fn, "rb"))) { printf("%s|%u|ko|absent|0|0000|0|0|0|0|0|00|00|0|-|||0\n", id, song); continue; }
        n = (unsigned)fread(buf, 1, sizeof buf, f);
        fclose(f);
        off = (buf[6] << 8) | buf[7];
        load = (buf[8] << 8) | buf[9]; init = (buf[10] << 8) | buf[11]; play = (buf[12] << 8) | buf[13];
        if (load == 0) { load = buf[off] | (buf[off + 1] << 8); off += 2; }
        if (init == 0) init = load;
        end = load + (n - off) - 1;

        r1 = emuler(buf, n, off, load, init, play, song, fps, calls, 0, 0, 0);
        if (fl_client) raison = "scan_client";
        else if (fl_save) raison = "scan_save";
        else if (fl_jam || fl_brk || fl_badexec) raison = "scan_jam";
        else if (!r1.ok_init) raison = "scan_initlong";
        else if (!r1.ok_play || r1.play_max > (fps == 60 ? PLAY_MAX60 : PLAY_MAX50)) raison = "scan_playlong";
        else if (!r1.sid_early) raison = "scan_silent";

        /* relais (§5.2, §5.3) */
        cur_load = load; cur_end = end;
        autres[0] = relais[0] = 0;
        complet = !sites_over;
        for (i = 0; i < (unsigned)nsites; i++) {
            const char *r = non_remplacable(&sites[i]);
            if (r) {
                complet = 0;
                snprintf(autres + strlen(autres), sizeof autres - strlen(autres), "%s%04X:%02X:%s",
                         autres[0] ? "," : "", sites[i].ad, sites[i].op, r);
            } else {
                rel[nrel++] = sites[i];
            }
        }
        qsort(rel, nrel, sizeof rel[0], sitecmp);
        if (nrel > MAX_RELAYS) {
            for (k = MAX_RELAYS; k < nrel; k++)
                snprintf(autres + strlen(autres), sizeof autres - strlen(autres), "%s%04X:%02X:trop",
                         autres[0] ? "," : "", rel[k].ad, rel[k].op);
            nrel = MAX_RELAYS;
            complet = 0;
        }
        if (nrel) {
            rlen = 32 + 7 * nrel;
            rz = zone(rlen, load, end);
            if (!rz) { rlen = 0; nrel = 0; complet = 0; }
        }
        if (!nsites) complet = 0;
        for (k = 0; k < nrel; k++)
            snprintf(relais + strlen(relais), sizeof relais - strlen(relais), "%s%04X:%02X", k ? "," : "", rel[k].ad, rel[k].op);

        /* vérification (§9.2) : même suite d'écritures SID avec les relais, copie = dernières valeurs écrites */
        if (!raison[0] && nrel) {
            int lit = rd02a6;
            verif = 1;
            r2 = emuler(buf, n, off, load, init, play, song, fps, calls, rel, nrel, rz);
            verif = 0;
            rd02a6 = lit;
            ver = "ok";
            if (r2.hash != r1.hash || r2.sidw != r1.sidw) ver = "diff";
            else if (fl_client || fl_save || fl_jam || fl_brk || fl_badexec || !r2.ok_init || !r2.ok_play) ver = "plante";
            else if (complet)
                for (k = 0; k < 25; k++)
                    if (ram[rz + k] != lastreg[k]) { ver = "copie"; break; }
        }

        if (dump && nrel && end < 0x10000) {
            static unsigned char m[65536];
            FILE *o;
            memset(m, 0, sizeof m);
            memcpy(m + load, buf + off, end + 1 - load);
            fabriquer(m, rel, nrel, rz);
            snprintf(path, sizeof path, "%s/%s.code", dump, id);
            if ((o = fopen(path, "wb"))) { fwrite(m + load, 1, end + 1 - load, o); fclose(o); }
            snprintf(path, sizeof path, "%s/%s.relay", dump, id);
            if ((o = fopen(path, "wb"))) { fwrite(m + rz, 1, rlen, o); fclose(o); }
        }
        printf("%s|%u|%s|%s|%d|%04X|%u|%d|%u|%llu|%llu|%02X|%02X|%d|%s|%s|%s|%d\n",
               id, song, raison[0] ? "ko" : "ok", raison, complet, rz, rlen, nsites, nrel,
               r1.init_cyc, r1.play_max, r1.port_init, r1.port_play, rd02a6, ver, relais, autres, r1.v1);
        fflush(stdout);
    }
    return 0;
}
