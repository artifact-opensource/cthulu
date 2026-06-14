---
title: PRIVACY POLICY
description: Privacy policy and data handling practices for the Cthulu trading system
tags: [privacy, policies, data-handling, legal]
sidebar_position: 20
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

## Overview

> Cthulu is an open-source autonomous trading system that runs locally on your machine. We are committed to protecting your privacy and being transparent about data handling.

### Data Collection
Cthulu does not collect, transmit, or store personal data on external servers by default. All data remains on your local machine:

- Trading data: stored locally in `Cthulu.db` (SQLite)
- Log files: stored in `logs/`
- Configuration: local files (use environment variables for secrets)

### Third-Party Services
Cthulu may interact with third-party services (MT5, news APIs, monitoring stacks). Your use of those services is subject to their terms and your API keys.

### Data Security
- Use environment variables or `.env` for credentials
- Do not commit API keys to version control
- Restrict file permissions on config and DB files

### Your Rights
You control data on your machine: delete, export, or modify as needed. Review the source to verify data handling.

#### Contact
Open an issue on GitHub for privacy concerns.
