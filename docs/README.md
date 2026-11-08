# Supporting material

- [audit.md](audit.md) records the repository findings and validation.
- [screenshots/](screenshots/) contains captures of the current dashboard.
- [architecture/](architecture/) contains the original pipeline and cloud-design images.
- [reports/progress_approach.docx](reports/progress_approach.docx) is the original mid-review report.

The report and architecture images are historical coursework artifacts. They mention Spark, Dataproc, cloud storage and SQLite components that are not implemented by the current pandas/Streamlit workflow. They have been retained without changing their original contents; use the root README and source code to describe the working project.

The original Colab cell fragment, `03_launch_dashboard.py`, has been replaced by a valid Python launcher:

```sh
python scripts/launch_dashboard.py
```

To share a demonstration from an environment such as Colab, install `cloudflared` separately and run:

```sh
python scripts/launch_dashboard.py --share
```

The launcher starts its own Streamlit process, waits for startup and opens the optional tunnel. It does not disable Streamlit's CORS/XSRF protections or kill unrelated processes. Stop it with Ctrl+C. Tunnel installation and live tunnel availability were not part of the automated checks.
