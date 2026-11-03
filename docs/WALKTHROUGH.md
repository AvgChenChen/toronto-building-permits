# Walkthrough: how this project works, in plain language

Read this before you talk about the project. It explains each step, the choices behind it, and
ends with questions you might be asked.

## The question

Toronto needs more housing. A home can't be built without a building permit, so the city's
permit records show what's been approved and how long approval takes. The project asks:
**how many new homes has Toronto approved since 2017, what kind, where, and how long does a
permit take?**

## The data, and the first surprise

The city publishes two files, each updated daily:
- **Cleared permits:** permits closed or cancelled since 2017 (about 450,000 rows).
- **Active permits:** permits still open (about 200,000 rows).

Using only the cleared file would be a mistake, because a permit only appears there once it's
closed, and slow ones close last. Recent years would look fast simply because the slow permits
aren't in the file yet. This is called **survivorship bias**. Every permit issued since 2017 is
in one file or the other, so the project combines them.

## The pipeline

1. **Download** ([`sources.py`](../src/permits/sources.py)). It asks Toronto Open Data where the
   latest files are, downloads them and records when. Only the 11 columns the analysis needs are
   read. Addresses and builder names are never loaded, because some builders are individuals.
2. **Clean** ([`clean.py`](../src/permits/clean.py)). Every step is logged, and the counts
   appear in the report:
   - **Revisions are dropped.** A revision repeats the original permit's details.
   - **Duplicates are dropped.** A permit can be in both files while it moves from open to
     closed. One permit number can also carry an early-start "conditional" permit and the full
     permit, so a permit is identified by its number *and* its type.
   - Permits never issued, or issued before 2017, are left out.
   - Impossible dates are set aside: an application after the issue date, or a closing date in 2028.
3. **Analyse** ([`analysis.py`](../src/permits/analysis.py)): homes by year and area, approval
   times, and the monthly closing trend.
4. **Write it up** ([`report.py`](../src/permits/report.py), [`charts.py`](../src/permits/charts.py)).
   Every sentence in the findings is filled in from a calculation.

## The second surprise: a permit clean-up

The first idea was to count homes when permits were *completed*. The data showed why that
doesn't work. From June 2025, the number of permits closed each month roughly doubled, and the
median permit being closed went from about 1 year old to about 4.5 years old. Construction didn't
suddenly double. The city appears to be closing out old paperwork.

The project detects this automatically ([`cleanup_start`](../src/permits/analysis.py)). It takes
the typical monthly count from the first five years, then looks for three months in a row at 1.5
times that or more. Because of the clean-up, homes are counted when the permit is **issued**
instead, which the clean-up doesn't affect.

**This is the best story to tell about the project:** the obvious approach gave a misleading
answer, the data showed why, and the method changed to avoid it.

## The measures

| Measure | Plain meaning | Why it's done this way |
|---|---|---|
| New homes approved | The "dwelling units created" figure on each permit issued that year | Counted at approval, so the clean-up doesn't distort it |
| Net new homes | New homes minus homes the same projects remove | A tower that replaces six houses adds less than its unit count |
| Median approval time | Half of permits took less than this, half took more | The average would be pulled up by a few permits that took years |
| 90th percentile | One permit in ten took longer than this | Shows the bad cases a builder plans around |
| Share of city | An area's new homes divided by all new homes approved | Includes homes with no postal code, so the shares are honest |

## Limitations

- **Approved isn't built.** Some approved homes will never be built, and big projects take years.
- **16% of approved homes have no postal code**, mostly on large apartment permits. Areas with
  big new developments are undercounted in the "where" table, and the report says so.
- **The unit count comes from the application** and isn't checked against what was built.
- **Approval time includes the applicant's time** answering the city's comments, so it isn't a
  measure of city staff speed alone.

## Questions you might be asked

- **"Why did 2020 and 2021 have so many approvals?"** The data shows the spike is almost all
  apartment and mixed-use buildings. It doesn't show why. You could look into interest rates and
  condo pre-sales in those years, but say clearly that's your own reasoning.
- **"Why are new houses approved faster than apartment buildings?"** A house usually needs one
  set of drawings checked. A tower involves structural, fire, mechanical and zoning reviews, and
  often several rounds of comments.
- **"Is small-scale housing really growing?"** Homes from suites, multiplexes and additions nearly
  doubled from 2017 to 2025. Toronto has changed its rules on laneway suites, garden suites and
  multiplexes in recent years. Check the dates of those changes before linking them to the trend.
- **"How do you know your numbers are right?"** Every cleaning step is counted in the report,
  the tests check each step on small examples, and the totals add up across the tables.
- **"What would you do next?"** Fill in missing postal codes from the city's address data, map
  the results by neighbourhood, or follow a group of permits from approval to completion once the
  clean-up is over.
