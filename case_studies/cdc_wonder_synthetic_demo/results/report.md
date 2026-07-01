# CDC WONDER synthetic-data case study

> **This case study is fully synthetic.** The numbers below are
> invented to demonstrate the disclosure-checked aggregate
> workflow. They are NOT real CDC WONDER data and MUST NOT be
> cited as such.

## Data summary

- Source: CDC WONDER synthetic UCD cerebrovascular series (synthetic)
- Database family: UCD
- Year range: 1999-2018
- Cells annotated: 20 (20 OK, 0 Unreliable, 1 Suppressed + dropped)

## Year-over-year change (synthetic UCD series)

| Year | Deaths | YoY change | Disclosure |
| ---: | ---: | ---: | :--- |
| 1999 | 150,000 | — | OK |
| 2000 | 148,500 | -1,500 | OK |
| 2001 | 145,800 | -2,700 | OK |
| 2002 | 142,300 | -3,500 | OK |
| 2003 | 138,900 | -3,400 | OK |
| 2004 | 134,200 | -4,700 | OK |
| 2005 | 130,400 | -3,800 | OK |
| 2006 | 127,100 | -3,300 | OK |
| 2007 | 124,500 | -2,600 | OK |
| 2008 | 122,900 | -1,600 | OK |
| 2009 | 120,400 | -2,500 | OK |
| 2010 | 118,700 | -1,700 | OK |
| 2011 | 117,800 | -900 | OK |
| 2012 | 117,900 | +100 | OK |
| 2013 | 118,700 | +800 | OK |
| 2014 | 119,900 | +1,200 | OK |
| 2015 | 121,500 | +1,600 | OK |
| 2016 | 123,400 | +1,900 | OK |
| 2017 | 125,300 | +1,900 | OK |
| 2018 | 126,900 | +1,600 | OK |

## Conservative-language summary

The synthetic series is consistent with a long-term decline
in the underlying-cause cerebrovascular death count followed
by a plateau / modest rise after 2012. This pattern SUGGESTS
(it does not prove) that the trajectory changed around 2012.

## Disclosure posture

- Cells with `Deaths <= 9` were dropped before
  any output was written.
- Cells with `Deaths <= 19` are kept but flagged
  `Unreliable` so a reviewer can decide whether to include them.
- UCD and MCD rows are kept in separate tables; they are not
  combined into the same chart without an in-figure note that
  the case-selection basis differs.

## Reproducibility

- Generated at: `2026-07-01T14:31:36.362957+00:00`
- Python version: `3.12.9`
- Package version: `0.3.0`
- Random seed: `2026` (unused in this run;
  recorded for forward compatibility with bootstrap-style
  extensions).
