# course-template

Shared layout, scripts and GitHub workflows for BioInfoCommunity course sites.
Course repos only keep their content and `_data/<lang>.yml`.

## Contents

- `_layouts/default.html` – page layout
- `_config.yml` – base Jekyll config
- `scripts/` – navigation generator, PR lint and WordPress sync
- `.github/workflows/` – reusable deploy and lint workflows

## Using it in a course

`.github/workflows/deploy.yml` in the course repo:

```yaml
on:
  push:
    branches: [main]
jobs:
  deploy:
    uses: BioInfoCommunity/course-template/.github/workflows/deploy.yml@main
    with:
      lang: en
    permissions:
      contents: write
```

Besides the usual course fields, `_data/<lang>.yml` needs `course.image` and a
`languages` list (`code` + `name`) for the language menu.

Optional: `course.space_url` (and `course.space_text`) adds a link to the course's
community space next to the hero kicker, e.g. "Online tutorial | Back to the AlphaFold space".

To sync pages from WordPress, run from the course repo root:

```
python ../course-template/scripts/sync_wp_pages.py https://www.ebi.ac.uk/training/online/courses/<course>/
```
