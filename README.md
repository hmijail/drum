# Dafny Resource Usage Measurement

## What does Darum do?

Dafny verifies code by translating it into Assertion Batches in the Boogie language, that then are verified by the Z3 solver.

For a long time, the common advice to make a piece of Dafny code pass verification was to add information to help Z3 find a solution. However, since Dafny 3.x there’s been a growing effort by the Dafny developers to add facilities to control what information reaches the Z3 solver. This is because the solver can sometimes have "too much information" and go down unproductive paths while looking for a solution. This bogs down the development process by causing longer verification times or timeouts instead of definite answers, and is a very common pain point in Dafny (and the wider Z3 / SMT solver ecosystem).

Managing what the solver “knows” tantamounts to guiding it down the right path by removing alternatives. The problem then is that Dafny's automation inherently makes it difficult to know what is actually the right path and what does the solver actually know. Indeed, at the Dafny level (that is, without digging into Boogie and Z3), the only information we get about the process is the result (verification successful, failure or timeout), plus how costly was it for the solver to reach that result, measured in "Resource Units" or "Resource Usage".

Darum helps the user find patterns in the solver costs, to discover hints to guide the debugging of verification brittleness. It does so by analysing and comparing the cost of verification at different granularities of the Assertion Batches, in a mostly automated way, by using existing Dafny facilities.


## Terminology

AB: Assertion Batch
Member: Dafny's methods or functions
Resource Usage: the cost of a verification run, as reported by Z3. More deterministic than timing costs.
OoR: Out of Resources. It's the result when Dafny/Boogie/Z3 are given a resource limit. Equivalent to a timeout.


## How does Darum do it?

The key insights that Darum exploits are:
* The RU needed to verify any Dafny code pertains to a probability distribution of evolving shape
* These distributions tend to grow wide and modal, causing the user to think that some problem appears and disappears.
* The distributions of ABs compound to members' distributions worse than linearly.

Consider the evolution of a piece of Dafny code:
* When the code is simple, the distribution is close to a spike: every verification run returns a predictable value.
* As the code grows and turns more complicated, the distribution starts to widen. Time needed for verification starts to vary. Perversely, in a bigger codebase in which individual members are only starting to misbehave, the total distribution might yield a smoother distribution, statistically compensating for the individual variation.
* At some point, some AB/member's verification gets complex enough that its distribution turns modal: sometimes verification runs fast, sometimes it runs much more slowly. Even worse, when this randomness appears in one AB/member, because of how Dafny + Boogie + Z3 work internally, that randomness will keep affecting the total distribution even while working on other ABs/members.
* As work progresses, other members' distributions will keep widening and also turn modal, each of them affecting the total distribution and compounding into new modes and wider distributions.

The final result is that one starts editing line X of a Dafny file and can't pinpoint why changes to that member sometimes cause a timeout and others verify correctly; what seemed a stable configuration suddenly stops working even though everything seems to be the same.



1. Analyse variability of verification RU at various granularities.
2. Analyse variability of ABs inside of a member.
3. Compare cost and variability of verifying a member vs verifying its ABs.



	1. IAmode or split here or manual partition
When running IA, an intriguing result is that the sum of ABs is typically much more expensive   than the original, but also much more stable. This suggests 2 more possibilities:
- stabilise by pessimization: IA always
- conversely, sometimes ABs  require higher RU  than the containing member,  or even fail to verify. This means that the other assets in the member built up some context that helped / was necessary for the assertion to pass verification; it’s a case where assertions in an AB help each other.

Our main goal is to stabilise this measure (and maybe  bring it down)


## What exactly is Darum?

Darum consists of 3 loosely coupled tools:


## Installation

## Usage

## Interpreting the results

### The plots

#### Plain plots

##### Worst offenders

ABs are scored according to their characteristics. The formula is just something that seems to make sense empirically:
Score = ((maxRC-minRC)/minRC) * (ABbooster) / ( (pastOoRs+1) * 10^pastFails)

Note that this formula accounts for the loss of usefulness of ABs that come after a non-successful AB in the same member.

Then, ABs are sorted by the attention they need: first failures, then OoRs, then by score.

The top N are plotted. For plots with failures/OoRs, the rightmost bar is wider to highlight those failures.

The plot starts in transparent mode to make it easier to see where bars overlap. Clicking on the legend makes the corresponding plot easier to see.

Verification results that happen rarely are specially important. Hence, the Y axis is logarithmic to more easily capture single atypical results.


#### Comparative plots

### The table/s

### Comments

### General discussion

Rule of thumb: isolated assertions: AB have span <3%. Full funcs/methods < 10%.

Dafny's official [docs](https://dafny.org/dafny/DafnyRef/DafnyRef.html#sec-brittle-verification) and [tools](https://github.com/dafny-lang/dafny-reportgenerator/blob/main/README.md) use statistical measures like stddev and RMS% to measure verification brittleness. However, we argue that it's more useful to think of simple min/max values. For example, consider the case of running 10 iterations of the verification process, in which 9 of the results are closely clustered but one single result deviates far away, being either much cheaper or much more expensive than the rest. Taking the stddev or RMS of these 10 cases would dampen the extremes, while we argue that they are precious hints that needs to be highlighted instead. Indeed, each time that the verification runs, these rare but extreme values are the ones with potential to turn things unexpectedly slow or fast. Furthermore, AB variability seems to compose disproportionally into more extreme variability at the member level, multiplying the effect of AB's span. This all suggests that, for reliability, it's necessary to minimize the span of Resource Usage costs.

It's worth noting that, while we're focusing on RU variability to combat brittleness, these tools are also useful to account for plain RU usage and rank where the verification time is being spent in the code.

## Some remedies to keep in mind

### Dafny library

### Section on Verification debugging in Ref Manual

