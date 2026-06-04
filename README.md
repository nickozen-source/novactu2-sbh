# NOVACTU SBH — Dashboard Météo / Surf / Air / Sargasses

Nouveau repository propre basé sur le fichier HTML existant. Le dashboard est statique pour être diffusé facilement via Netlify et un logiciel de CMS signage.

## Fonctionnement

- `index.html` : dashboard affiché par Netlify.
- `update_dashboard.py` : récupère les données publiques, écrit `data/latest.json`, puis met à jour `index.html`.
- `.github/workflows/update-dashboard.yml` : lance la mise à jour tous les jours à 06:00 Saint-Barthélemy.
- `netlify.toml` : configuration Netlify sans build.

## Sources utilisées

- Open-Meteo Forecast API : météo, vent, humidité, lever/coucher du soleil.
- Open-Meteo Marine API : houle, période, direction, température mer.
- Open-Meteo Air Quality API : PM2.5, PM10, ozone, poussières / dust.
- NOAA/AOML Sargassum Inundation Report + Journal de Saint-Barth quand accessible : indication sargasses. Cette partie reste une estimation locale prudente, car les données plage par plage ne sont pas toujours disponibles en API publique fiable.

## Mise en place GitHub

1. Créer un nouveau repository GitHub, par exemple `novactu-sbh-dashboard`.
2. Envoyer tous les fichiers de ce dossier dans le repository.
3. Aller dans **Actions** et vérifier que le workflow `NOVACTU SBH — Update dashboard` est actif.
4. Lancer une première fois avec **Run workflow** pour tester immédiatement.

Le cron GitHub est en UTC. Saint-Barthélemy est en UTC-4 : `0 10 * * *` correspond à 06:00 heure locale.

## Mise en place Netlify

1. Dans Netlify, créer un nouveau site depuis ce repository GitHub.
2. Paramètres de build :
   - Build command : laisser vide.
   - Publish directory : `.`
3. Netlify redéploiera automatiquement à chaque push GitHub, donc après chaque mise à jour quotidienne.
4. Utiliser l’URL Netlify dans le CMS signage.

## Test local

```bash
python3 update_dashboard.py
python3 -m http.server 8000
```

Puis ouvrir `http://localhost:8000`.

## Notes importantes

- Le workflow commit uniquement s’il y a une modification.
- `data/latest.json` conserve les données brutes utilisées pour le dernier affichage.
- Les sources externes peuvent parfois être indisponibles ; dans ce cas, le script continue avec les autres données disponibles au lieu de casser le déploiement.
