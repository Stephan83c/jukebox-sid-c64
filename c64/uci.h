/*
 * SID Jukebox C64
 * Copyright (C) 2026 Stephan83c
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify it under the
 * terms of the GNU General Public License as published by the Free Software Foundation,
 * either version 3 of the License, or (at your option) any later version. It is
 * distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
 */
/* Ultimate Command Interface ($DF1C-$DF1F), cible réseau. Inclus par client.c avant uci.c et main.c. */
#ifndef UCI_H
#define UCI_H

/* Vrai si l'interface répond (option « Command Interface » activée). */
unsigned char uci_present(void);

/* Ouvre une connexion TCP ; renvoie le numéro de socket, ou -1. */
int net_ouvrir(const char *hote, unsigned port);

/* Lecture non bloquante : nombre d'octets copiés, 0 si rien, -1 si la
 * connexion est fermée (par le serveur ou parce que l'Ultimate ne répond plus). */
int net_lire(unsigned char sock, char *dst, unsigned char max);

/* Écriture ; renvoie 1 si l'Ultimate a accepté. */
unsigned char net_ecrire(unsigned char sock, const char *src, unsigned char n);

void net_fermer(unsigned char sock);

/* Une commande n'a pas abouti dans son délai : l'Ultimate ne répond plus
 * (sockets épuisés après des resets) ; seule une coupure de courant le relance. */
extern unsigned char uci_bloquee;

/* Dernier statut texte de l'Ultimate (ex. « 00,OK »), pour diagnostic. */
extern char uci_statut[];

#endif
