# mantecato-cli

Remote command-line client for Mantecato. It connects to a Mantecato server over HTTPS and authenticates with an API key. It does not install Django and never connects to PostgreSQL directly.

## Install

```sh
uv tool install mantecato-cli
# or
pipx install mantecato-cli
```

## Configure

```sh
export MANTECATO_URL=https://analytics.example.com
export MANTECATO_API_KEY=mtk_...
mantecato doctor
```

Prefer your shell or deployment secret store for `MANTECATO_API_KEY`. You can instead set `MANTECATO_API_KEY_FILE` to a file readable only by your user. Do not put a key in a segment or profile file.

The optional config file contains non-secret profiles and reusable filter segments. Default locations are `~/.config/mantecato/config.yaml` on Linux, `~/Library/Application Support/mantecato/config.yaml` on macOS, and `%APPDATA%/mantecato/config.yaml` on Windows.

```yaml
profiles:
  production:
    url: https://analytics.example.com
segments:
  tier1_en:
    filters:
      - country:in:US,GB,CA,AU
```

```sh
mantecato sites --format json
mantecato timeseries -w <uuid> -r 30d -g day --dimension country --segment tier1_en
mantecato compare-breakdown -w <uuid> --dimension country --compare previous_period
```
