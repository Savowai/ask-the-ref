# Source verification — 2026-09-28

| Rulebook | Applicable edition | Evidence / official discovery |
|---|---|---|
| IFAB Laws of the Game | 2026/27 | https://theifab.com/documents/ |
| FIFA RSTP | July 2025, including interim framework | https://support.fifatms.com/en/support/solutions/articles/7000031125-regulations |
| UEFA Champions League | 2026/27, enforced 29 July 2026 | https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27-Online |
| UEFA Europa League | 2026/27, enforced 29 July 2026 | https://documents.uefa.com/r/Regulations-of-the-UEFA-Europa-League-2026/27-Online |
| Premier League Handbook | 2026/27, published 31 July 2026 | https://www.premierleague.com/en/news/62625 |

The machine-readable manifest records the complete direct PDF URLs and downloaded
SHA-256 values. No source PDF or extracted rule text is committed.

IFAB's effective date is confirmed in its official announcement:
https://www.theifab.com/news/the-ifab-introduces-further-measures-to-improve-match-flow-and-player-behaviour/

FIFA's new transfer framework was published in 2026 but only comes into force on
1 January 2027. Do not load it early. FIFA's TMS library explicitly distinguishes it
from the current July 2025 PDF. Official corroboration:
https://football-technology.fifa.com/legal/education/flar

The FIFA corpus must undergo a provision-level applicability audit in Phase 5:
Annexe 7 contains temporary provisions with dates; circulars and amendments may
change individual provisions without changing the base PDF. A book-level date check
alone does not solve this. Likewise, exclude the futsal annex from association-football Q&A.

UEFA's portal provides structured online sections and official PDF attachments.
Verified discovery mechanism: POST `https://documents.uefa.com/api/khub/maps/search`
with a quoted title query. Match exact title, `ft:locale=en-GB`, `FullSeasonYears`,
and `EnforcementDate`. GET `/api/khub/maps/{mapId}/attachments` identifies the PDF;
GET `/api/khub/maps/{mapId}/attachments/{attachmentId}/content` downloads it.
The manifest pins the verified attachment URLs. The Phase 6 updater must re-discover
attachments and verify edition/effectivity rather than hard-code today's map ids.

The Premier League manifest's start bound is its verified publication date; it does
not assert a single commencement date for all constituent handbook provisions.
Extract and apply provision dates during Phase 5 before the corpus is activated.

FIFA competition regulations will be selected by named competition in Phase 5.
Official discovery starts at https://inside.fifa.com/legal/documents and the tournament
site, e.g. https://www.fifa.com/en/tournaments/mens/intercontinentalcup/2026 .
The completed World Cup 2026 is not silently treated as the default FIFA competition.
No unverified tournament PDF is represented as an active source in this phase.
