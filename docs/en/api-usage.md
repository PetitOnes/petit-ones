# API Usage

Back to [README](../../README_en.md)

## API Usage Management

Settings to prevent excessive Claude API usage:

- **Adjust autonomous action frequency**: Schedule control in `autonomous-action.sh` — active hours (every run) vs inactive hours (probability-based). Set time ranges in `characters/{id}/settings.json` `active_hours`
- **Stop autonomous actions**: Comment out the crontab entry (`#` at the start)
- **Dashboard diary generation**: Manual button or once daily (23:50). Does not run frequently
- **Anthropic Console**: Check usage and set spending limits at https://console.anthropic.com/settings/usage

```bash
# Temporarily stop all autonomous actions
crontab -l | sed 's/^\(.*autonomous-action\)/#\1/' | crontab -

# Resume
crontab -l | sed 's/^#\(.*autonomous-action\)/\1/' | crontab -
```

## Estimated API Usage

With 2 characters and default settings (`active_hours: [[7,8],[12,13],[18,24]]`):

| Type | Frequency | Calls/Day | Notes |
|------|-----------|-----------|-------|
| Autonomous (active hours) | Every 20 min | ~24/char | 8h x 3/h |
| Autonomous (daytime inactive) | Hourly :00, 30% chance | ~3/char | 9h x 0.3 |
| Autonomous (nighttime) | Hourly :00, 10% chance | ~1/char | 7h x 0.1 |
| Diary generation | 23:50 | 1/char | |
| desire_updater | Every 5 min | 0 | Direct SQLite read, no API |
| **Total (2 characters)** | | **~58/day** | |

### Cost Estimate (Sonnet 4)

| Period | Estimate |
|--------|----------|
| 1 day | ~$1.50 |
| 1 month | ~$45 |

Heavy tool usage can increase costs; expect $70-100/month in practice.

### Saving Costs

- **Narrow `active_hours`**: e.g., `[[18,23]]` only -> less than half
- **Lower inactive probability**: Daytime 30%->10%, nighttime 10%->0% in `autonomous-action.sh`
- **Fewer characters**: 1 character = half the cost
- **Set limits on Anthropic Console**: https://console.anthropic.com/settings/usage
