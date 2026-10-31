# Deferred speaker confirmation experiment

This is an offline prototype based on the diagnosis and rule comparisons in
[AB_TEST_RESULTS.md](AB_TEST_RESULTS.md). Neither variant qualifies for device
integration: they reduce splits but increase merges across the saved corpus.
The production clusterer, model and device policy are unchanged.

## Fixed design

The threshold remains 0.6, with two or three long phrases required to confirm a
speaker. All supporting pairs must meet the threshold (complete linkage), and
each phrase must currently match no confirmed speaker. Earliest eligible groups
win ties. The two/three-phrase variants, eight-phrase pending limit and eight-
arrival expiry were fixed before examining this experiment's corpus results.
There was no subsequent threshold or rule search.

1. A unique match to a confirmed speaker is labelled immediately. Long phrases
   update that speaker's centroid; short phrases do not.
2. An unmatched or ambiguous phrase stays pending. Only long phrases can support
   confirmation of a new speaker. Short phrases can receive a later match.
3. After a confirmation or centroid update, pending phrases are checked against
   the confirmed speakers. A unique match resolves the pending label. These
   resolved phrases do not update centroids, avoiding self-reinforcing evidence.
4. Emitted labels are immutable. Pending phrases expire as unknown at eight
   subsequent arrivals; the current phrase at that boundary cannot revive them.
   Stop/flush emits any remaining unresolved phrases as unknown.

`provisional_clusters.h` implements this causal policy. The replay driver
retains final results for scoring, but does not retrospectively rewrite an
already emitted label. It uses no reference speaker IDs. In a product, pending
phrases would need explicit readiness and expiry events; that integration is
not implemented.

## Evaluation

Run from the repository root on the private voiceprint sets produced by
`spkrules.py embed`:

```sh
python3 tests/test_spkprovisional.py
python3 tools/device_tests/speaker/spkprovisional.py private/speaker/rule-sets.json \
  --shuffles 200 --bootstrap 10000 > private/speaker/provisional-compare.json
```

The same C++ production rule and identical orders form the baseline. Clean and
session sets use their original order plus 200 shared seeded shuffles; corpus
sets use their sampled turn order. Both candidate variants were evaluated once
on all 189 sets / 4,654 phrases. Even/odd corpus conversation indices provide
development/reserved summaries, 90 conversations each. Those subsets are not
speaker-disjoint, and the corpus was already used for earlier rule experiments;
the reserved summary is not an untouched generalization test.

Paired bootstrap intervals resample conversation indices within each of the
three source families, keeping each clean/simulated-channel pair together.
There are 45 such paired blocks per subset and 10,000 bootstrap replicates.
Conversations can share speakers; the intervals are conditional descriptions
of this reused sample. Shuffles are not independent real-world conversations.

Delay is measured in subsequent phrase arrivals, not seconds. The saved
voiceprint sets do not retain the timing needed to establish wall-clock label
latency. Final coverage and coverage at the phrase's arrival are both reported;
final coverage must not be presented as immediate availability.

## Result and limits

The two-phrase variant recovers the original duplicate-speaker replay pattern,
but on the reserved corpus it changes split phrases per 100 from 7.64 to 0.97
and merge phrases per 100 from 1.11 to 3.47. The three-phrase variant changes
those rates to 0.09 and 4.21 while reducing final coverage from 88.4% to 74.4%.
These fail the no-increased-merge gate. Better labelled accuracy alone is not a
safe replacement criterion.

The model is float on the Mac and quantized on the device. Session replays use
clean source audio at estimated device spans; they do not reproduce the actual
microphone waveform or Conversation 2's device merge. Corpus turns and shuffled
orders are synthetic. Host sanitizer and replay tests establish causal state
handling and arithmetic behavior, not P4 accuracy, memory or realtime timing.

Pending embedding state is bounded: at 512 dimensions there are at most eight
retained pending vectors plus the incoming vector, and eight confirmed centroid
sums (34,816 float bytes). Vector metadata, temporary storage, input embeddings
and the offline result archive are additional. The archive grows with the run;
this prototype is not a drop-in allocation-free firmware implementation. No P4
performance or memory qualification has been performed.

Further work needs independent, speaker-disjoint examples and richer evidence
for deciding when similar voices are different people. Waiting alone is not a
validated solution. The two/three-phrase prototypes and their failed cases are
retained to make that limitation reproducible.
