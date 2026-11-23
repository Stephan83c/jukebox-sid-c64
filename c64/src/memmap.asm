// Carte mémoire du client v2.0 (SPEC-v2.md §7.1, §8) : une seule valeur, HISTART, dont tout le reste découle.
//   $0800..HISTART-1   morceau + bloc de relais
//   HISTART..$BFFF     client (réseau, écrans, tampons) : rien qui s'exécute pendant ou juste après un appel du morceau
//   $C000-$CFFF        lecteur (player.asm)
// HISTART provisoire jusqu'à l'étape 5 (doit rester égal à SCAN_HISTART de server.py et au HISTART de l'analyse).
        .const HISTART = $AF00
        .const HIMEM   = HISTART - 1                       // dernière adresse permise au morceau et au bloc de relais
        .const LIMITE  = toHexString(HIMEM, 4).toUpperCase()   // envoyée dans RANDOM3
        .const MEM_BAS = $0800
        .const RELAY_MAX = 32 + 7 * 48                     // §5.3 : 368 octets
