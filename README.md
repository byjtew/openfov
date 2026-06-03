# OpenFOV

Fork of [OpenFOV](https://github.com/epalosh/openfov) replacing iRace support for UDP dispatch of the HPR values.

### Quickstart

```shell
uv init --python 3.12
uv pip install requirements.txt
uv pip install requirements-dev.txt
uv run openfov
```

To edit the UDP target, update the `.env` file.

### UDP Data-format

```json
{
  "rotation": [ <heading_deg>, <pitch_deg>, <roll_deg> ]
}
```
