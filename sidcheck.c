/* SID Jukebox : contrôle des morceaux par émulation 6502.
 * Copyright (C) 2026 Stephan83c
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Joue chaque morceau comme le lecteur du client (init puis play, $01 = $34, E/S et ROM coupées),
 * et signale ce qui casserait le client :
 *   client  : écriture entre lo et $CFFF (code et données du client, lo = HISTART)
 *   zpsave  : écriture en $D200-$D2FF (sauvegarde de la page zéro, RAM sous les E/S)
 *   vect    : écriture en $FFFA-$FFFF (vecteurs IRQ/NMI lus en RAM)
 *   exec    : exécution de code entre lo et $CFFF
 *   ecran   : écriture en $F400-$FFF9 (écran et caractères de lecture : seulement visuel)
 *   initlong / playlong : init ou play qui ne rend pas la main (boucle d'attente, ex. raster lu en RAM)
 *   jam / brk : instruction de blocage ou BRK
 *
 * Usage : sidcheck [lo_hex] [appels] < liste   (lignes « id|chemin|sous-morceau »)
 * Sortie : « id|motifs|première adresse fautive » pour chaque morceau qui pose problème.
 * Compiler : cc -O2 -o sidcheck sidcheck.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char ram[65536], kernal[8192], basic[8192];
static unsigned char a, x, y, s, p, port;
static unsigned short pc;
static unsigned long long ninstr;
static unsigned lo = 0xAF00;
static int fl_client, fl_zp, fl_vect, fl_exec, fl_ecran, fl_jam, fl_brk;
static unsigned bad;
static unsigned char tp[256];      /* pages écrites par le morceau en cours */
static unsigned long gp[256];      /* nombre de morceaux qui écrivent chaque page (option SIDCHECK_PAGES) */

#define FC 0x01
#define FZ 0x02
#define FI 0x04
#define FD 0x08
#define FB 0x10
#define FV 0x40
#define FN 0x80

static int io_vis(void) { return (port & 3) != 0 && (port & 4); }

static unsigned char rd(unsigned short ad)
{
    if (ad >= 0xA000 && ad < 0xC000 && (port & 3) == 3) return basic[ad - 0xA000];
    if (ad >= 0xE000 && (port & 2)) return kernal[ad - 0xE000];
    if (ad >= 0xD000 && ad < 0xE000 && io_vis()) {
        unsigned line = (unsigned)((ninstr * 3 / 63) % 312);
        switch (ad) {
        case 0xD011: return (unsigned char)(0x1B | ((line & 0x100) ? 0x80 : 0));
        case 0xD012: return (unsigned char)line;
        case 0xD41B: case 0xD41C: return (unsigned char)(ninstr * 7);
        case 0xDC04: case 0xDD04: return (unsigned char)(~ninstr);
        case 0xDC05: case 0xDD05: return (unsigned char)(~ninstr >> 8);
        default: return 0;
        }
    }
    if (ad == 1) return port;
    return ram[ad];
}

static void mark(unsigned ad, int *f)
{
    if (!*f && !bad) bad = ad;
    *f = 1;
}

static void wr(unsigned short ad, unsigned char v)
{
    if (ad == 1) { port = v; return; }
    tp[ad >> 8] = 1;
    if (ad >= lo && ad < 0xD000) mark(ad, &fl_client);
    else if (ad >= 0xD200 && ad < 0xD300 && !io_vis()) mark(ad, &fl_zp);
    else if (ad >= 0xFFFA) mark(ad, &fl_vect);
    else if (ad >= 0xF400) fl_ecran = 1;
    ram[ad] = v;   /* une écriture va toujours en RAM (sauf E/S visibles, sans effet ici) */
}

static void push(unsigned char v) { ram[0x100 + s--] = v; }
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

/* Mode d'adressage de chaque opcode : 0 implicite, 1 imm, 2 zp, 3 zpx, 4 zpy, 5 abs, 6 abx, 7 aby, 8 izx, 9 izy, 10 rel, 11 ind */
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
    unsigned char op = rd(pc), v, m = mode[op];
    unsigned short ea = 0, base;
    if (pc >= lo && pc < 0xD000) { if (!fl_exec && !bad) bad = pc; fl_exec = 1; return 0; }
    pc++;
    ninstr++;
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
#define BR(c) if (c) pc = ea; break
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

/* Appelle une routine comme le lecteur (JSR) ; renvoie 0 si elle ne rend pas la main en max instructions. */
static int call(unsigned short ad, unsigned char ac, unsigned long long max)
{
    unsigned long long fin = ninstr + max;
    s = 0xF0;
    push(0xFF); push(0xEF);   /* retour vers $FFF0 */
    pc = ad; a = ac; x = 0; y = 0;
    while (pc != 0xFFF0) {
        if (!step()) return 1;   /* blocage déjà signalé par un drapeau */
        if (ninstr > fin) return 0;
    }
    return 1;
}

int main(int argc, char **argv)
{
    FILE *f;
    unsigned n;
    char line[1024];
    unsigned calls = argc > 2 ? (unsigned)atoi(argv[2]) : 1500;
    const char *home = getenv("HOME");
    char path[512];
    if (argc > 1) lo = (unsigned)strtoul(argv[1], 0, 16);
    snprintf(path, sizeof path, "%s/.local/share/vice/C64/kernal-901227-03.bin", home);
    if (!(f = fopen(path, "rb")) || fread(kernal, 1, 8192, f) != 8192) { fprintf(stderr, "ROM KERNAL introuvable\n"); return 1; }
    fclose(f);
    snprintf(path, sizeof path, "%s/.local/share/vice/C64/basic-901226-01.bin", home);
    if (!(f = fopen(path, "rb")) || fread(basic, 1, 8192, f) != 8192) { fprintf(stderr, "ROM BASIC introuvable\n"); return 1; }
    fclose(f);
    while (fgets(line, sizeof line, stdin)) {
        static unsigned char buf[70000];
        char *id = strtok(line, "|\n"), *fn = strtok(0, "|\n"), *sg = strtok(0, "|\n");
        unsigned off, load, init, play, i;
        int ok1, ok2 = 1;
        if (!id || !fn) continue;
        if (!(f = fopen(fn, "rb"))) { printf("%s|absent|0\n", id); continue; }
        n = (unsigned)fread(buf, 1, sizeof buf, f);
        fclose(f);
        off = (buf[6] << 8) | buf[7];
        load = (buf[8] << 8) | buf[9]; init = (buf[10] << 8) | buf[11]; play = (buf[12] << 8) | buf[13];
        if (load == 0) { load = buf[off] | (buf[off + 1] << 8); off += 2; }
        if (init == 0) init = load;
        memset(ram, 0, sizeof ram);
        for (i = lo; i < 0xD000; i++) ram[i] = 0xEA;    /* le client (contenu sans importance pour les écritures) */
        if (off < n) memcpy(ram + load, buf + off, (n - off) > 65536 - load ? 65536 - load : n - off);
        fl_client = fl_zp = fl_vect = fl_exec = fl_ecran = fl_jam = fl_brk = 0;
        bad = 0; ninstr = 0; p = FI; port = 0x34;
        ok1 = call((unsigned short)init, (unsigned char)((sg ? atoi(sg) : 1) - 1), 20000000ULL);
        if (ok1 && !fl_jam && !fl_brk && !fl_exec && play)
            for (i = 0; i < calls && ok2 && !fl_jam && !fl_brk && !fl_exec; i++) {
                port = 0x34;
                ok2 = call((unsigned short)play, 0, 200000ULL);
            }
        for (i = 0; i < 256; i++) { gp[i] += tp[i]; tp[i] = 0; }
        if (fl_client || fl_zp || fl_vect || fl_exec || fl_ecran || fl_jam || fl_brk || !ok1 || !ok2)
            printf("%s|%s%s%s%s%s%s%s%s%s|%04X\n", id,
                   fl_client ? "client " : "", fl_zp ? "zpsave " : "", fl_vect ? "vect " : "", fl_exec ? "exec " : "",
                   fl_ecran ? "ecran " : "", fl_jam ? "jam " : "", fl_brk ? "brk " : "", !ok1 ? "initlong " : "",
                   !ok2 ? "playlong " : "", bad);
        fflush(stdout);
    }
    if (getenv("SIDCHECK_PAGES"))
        for (n = 0; n < 256; n++) fprintf(stderr, "%02X %lu\n", n, gp[n]);
    return 0;
}
