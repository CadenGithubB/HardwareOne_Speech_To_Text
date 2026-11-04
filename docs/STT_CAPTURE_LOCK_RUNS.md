# Capture-lock run-by-run measurements

4 November 2026. Forty-four bracketed acoustic captures, separated by SDK and
comparison factor. The twenty-session single-boot soak is reported separately in
[STT_CAPTURE_LOCK_RESULTS.md](STT_CAPTURE_LOCK_RESULTS.md). Production adoption remains held.

All instrumented captures use 64-byte L2 and standalone 200 MHz PSRAM. B/P means
full/prefix clearing. On/Off means probes or speaker worker; both sides retain
prefix clearing for those controls. Each row retains its own denominator. These
small acoustic brackets do not establish statistical noninferiority.

Timing pairs are median / p90 in seconds. Final and speaker publication are
host receipt relative to reference phrase end, not physical display time.
Draft freshness measures lag behind represented audio; first draft is elapsed
from segment start. Neither is word-level shown-text alignment. The invalid
conv4 host clock withholds timing. Probe-off has no qualified sample alignment
or driver-loss measurement. Speaker-off missing labels are intentional.
Outside-playback counts cover the waveform window, not every annotated silence;
a dedicated silence false-caption benchmark was not performed.

Free-heap checkpoints and boot minima are not inference peaks. All listed
captures have zero observed watchdogs/panics; zero DMA values apply only to
instrumented runs. Feature-cache fallback is separate from audio loss. All raw
captions, audio and device logs stay in ignored private directories.

## Original SDK: primary

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 38 | 85/499 (17.03%) | 15/38 | 14 | 0/0 | 0 |
| conv2 P1 | 38 | 76/499 (15.23%) | 21/38 | 3 | 0/0 | 0 |
| conv2 P2 | 38 | 77/499 (15.43%) | 17/38 | 13 | 0/0 | 0 |
| conv2 B3 | 40 | 77/499 (15.43%) | 25/38 | 3 | 0/2 | 2 |
| conv3 B0 | 47 | 113/466 (24.25%) | 33/47 | 9 | 0/0 | 0 |
| conv3 P1 | 47 | 110/466 (23.61%) | 28/47 | 11 | 0/0 | 0 |
| conv3 P2 | 47 | 107/466 (22.96%) | 26/47 | 11 | 0/0 | 0 |
| conv3 B3 | 47 | 116/466 (24.89%) | 30/47 | 8 | 0/0 | 0 |
| conv4 B0 | 34 | 88/470 (18.72%) | 11/34 | 15 | 0/0 | 0 |
| conv4 P1 | 33 | 79/470 (16.81%) | 15/33 | 10 | 0/0 | 0 |
| conv4 P2 | 35 | 78/470 (16.60%) | 15/35 | 13 | 0/0 | 0 |
| conv4 B3 | 34 | 80/470 (17.02%) | 19/34 | 10 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | 2.026 / 3.024 | 0.695 / 1.378 | 1.500 / 2.777 | 3.127 / 4.983 | 1.089 / 2.370 |
| conv2 P1 | 1.954 / 2.745 | 0.698 / 1.362 | 1.513 / 2.295 | 3.064 / 5.621 | 1.089 / 2.138 |
| conv2 P2 | 1.951 / 2.813 | 0.680 / 1.364 | 1.518 / 2.150 | 3.044 / 4.044 | 1.081 / 1.819 |
| conv2 B3 | 1.955 / 2.659 | 0.657 / 1.366 | 1.522 / 2.121 | 3.072 / 4.389 | 1.174 / 1.836 |
| conv3 B0 | 1.912 / 2.215 | 0.648 / 1.094 | 1.527 / 2.102 | 3.104 / 4.244 | 1.176 / 2.136 |
| conv3 P1 | 1.919 / 2.195 | 0.648 / 1.125 | 1.527 / 1.745 | 3.147 / 4.272 | 1.181 / 1.826 |
| conv3 P2 | 1.912 / 2.401 | 0.644 / 1.098 | 1.543 / 2.556 | 3.060 / 4.160 | 1.164 / 1.930 |
| conv3 B3 | 1.926 / 2.450 | 0.645 / 1.124 | 1.525 / 2.133 | 3.129 / 4.258 | 1.181 / 1.840 |
| conv4 B0 | 2.360 / 3.100 | 0.762 / 1.386 | 1.550 / 2.458 | 3.973 / 5.539 | 1.727 / 3.310 |
| conv4 P1 | 2.439 / 3.345 | 0.828 / 1.442 | 1.592 / 2.835 | 3.958 / 6.805 | 1.703 / 3.707 |
| conv4 P2 | 2.345 / 3.172 | 0.742 / 1.392 | 1.507 / 2.643 | 3.978 / 5.720 | 1.713 / 3.305 |
| conv4 B3 | 2.376 / 3.328 | 0.795 / 1.427 | 1.573 / 2.703 | 3.917 / 5.505 | 1.646 / 3.285 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | (1, 10] | 1.410 | (1000, 2000] | 6.546 | 6.585 |
| conv2 P1 | (1, 10] | 2.367 | (1000, 2000] | 6.328 | 6.368 |
| conv2 P2 | (1, 10] | 2.580 | (1000, 2000] | 6.375 | 6.408 |
| conv2 B3 | (1, 10] | 3.288 | (2000, 4000] | 7.005 | 7.046 |
| conv3 B0 | (1, 10] | 1.780 | (2000, 4000] | 5.636 | 5.681 |
| conv3 P1 | (1, 10] | 1.122 | (2000, 4000] | 5.286 | 5.331 |
| conv3 P2 | (10, 50] | 0.252 | (2000, 4000] | 5.703 | 5.752 |
| conv3 B3 | (1, 10] | 3.792 | (2000, 4000] | 6.094 | 6.137 |
| conv4 B0 | (1, 10] | 2.190 | (1000, 2000] | 6.884 | 6.925 |
| conv4 P1 | (1, 10] | 0.804 | (1000, 2000] | 7.345 | 7.381 |
| conv4 P2 | (1, 10] | 4.072 | (1000, 2000] | 6.769 | 6.820 |
| conv4 B3 | (1, 10] | 0.117 | (1000, 2000] | 7.105 | 7.145 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 10,496,000 / 96.129 | 5,907,520 / 118.452 | 13,157,120 / 239.068 | 1 | 24 | 3 | 0 / 0 |
| conv2 P1 | 3,504,640 / 28.627 | 5,902,720 / 116.498 | 13,051,072 / 238.630 | 1 | 0 | 0 | 0 / 0 |
| conv2 P2 | 3,350,016 / 27.065 | 5,715,840 / 112.095 | 12,280,448 / 220.400 | 1 | 4 | 1 | 0 / 0 |
| conv2 B3 | 10,496,000 / 95.441 | 5,931,840 / 119.048 | 12,619,712 / 228.784 | 1 | 5 | 1 | 0 / 0 |
| conv3 B0 | 13,056,000 / 120.562 | 5,872,320 / 114.688 | 11,182,080 / 206.932 | 1 | 0 | 0 | 0 / 0 |
| conv3 P1 | 3,938,560 / 31.762 | 5,973,120 / 120.310 | 11,200,768 / 205.396 | 1 | 0 | 0 | 0 / 0 |
| conv3 P2 | 3,927,296 / 31.488 | 5,913,600 / 115.042 | 11,190,272 / 205.653 | 1 | 0 | 0 | 0 / 0 |
| conv3 B3 | 12,800,000 / 117.607 | 5,877,440 / 114.459 | 11,254,656 / 208.835 | 1 | 0 | 0 | 0 / 0 |
| conv4 B0 | 8,960,000 / 80.573 | 5,852,480 / 117.093 | 13,706,816 / 256.549 | 1 | 0 | 1 | 0 / 0 |
| conv4 P1 | 3,393,536 / 27.234 | 5,941,440 / 118.517 | 13,884,544 / 258.012 | 1 | 0 | 2 | 0 / 0 |
| conv4 P2 | 3,357,696 / 27.558 | 5,928,320 / 119.812 | 13,199,552 / 247.945 | 1 | 0 | 0 | 0 / 0 |
| conv4 B3 | 8,704,000 / 83.881 | 5,871,360 / 117.504 | 13,594,368 / 256.926 | 1 | 0 | 1 | 0 / 0 |

## Original SDK: bounded conv3 follow-up

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv3 B0 | 48 | 113/466 (24.25%) | 31/48 | 12 | 0/0 | 0 |
| conv3 P1 | 47 | 111/466 (23.82%) | 28/47 | 12 | 0/0 | 0 |
| conv3 P2 | 47 | 109/466 (23.39%) | 27/47 | 10 | 0/0 | 0 |
| conv3 B3 | 47 | 113/466 (24.25%) | 27/47 | 10 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv3 B0 | 1.921 / 2.454 | 0.643 / 1.127 | 1.524 / 2.084 | 3.123 / 4.330 | 1.183 / 2.247 |
| conv3 P1 | 1.966 / 2.374 | 0.655 / 1.109 | 1.532 / 1.880 | 3.161 / 4.182 | 1.174 / 1.931 |
| conv3 P2 | 1.911 / 2.195 | 0.660 / 1.103 | 1.499 / 1.834 | 3.051 / 4.125 | 1.168 / 1.899 |
| conv3 B3 | 1.928 / 2.222 | 0.673 / 1.123 | 1.505 / 1.831 | 3.144 / 4.259 | 1.167 / 1.820 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv3 B0 | (1, 10] | 4.717 | (2000, 4000] | 5.643 | 5.684 |
| conv3 P1 | (1, 10] | 0.698 | (2000, 4000] | 6.011 | 6.059 |
| conv3 P2 | (1, 10] | 1.103 | (2000, 4000] | 5.103 | 5.153 |
| conv3 B3 | (1, 10] | 0.856 | (2000, 4000] | 5.702 | 5.737 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv3 B0 | 12,544,000 / 115.543 | 5,976,960 / 118.757 | 11,038,976 / 205.492 | 1 | 0 | 0 | 0 / 0 |
| conv3 P1 | 3,849,984 / 31.040 | 5,933,760 / 116.892 | 11,267,904 / 207.220 | 1 | 0 | 0 | 0 / 0 |
| conv3 P2 | 3,886,080 / 31.340 | 5,896,960 / 115.261 | 11,007,360 / 204.408 | 1 | 0 | 0 | 0 / 0 |
| conv3 B3 | 12,544,000 / 114.700 | 5,896,640 / 117.997 | 11,098,304 / 205.907 | 1 | 0 | 0 | 0 / 0 |

## Model-local SDK: primary

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 38 | 78/499 (15.63%) | 29/38 | 1 | 0/0 | 0 |
| conv2 P1 | 38 | 78/499 (15.63%) | 28/38 | 2 | 0/0 | 0 |
| conv2 P2 | 38 | 75/499 (15.03%) | 28/38 | 1 | 0/0 | 0 |
| conv2 B3 | 38 | 81/499 (16.23%) | 28/38 | 2 | 0/0 | 0 |
| conv3 B0 | 47 | 123/466 (26.39%) | 41/47 | 3 | 0/0 | 0 |
| conv3 P1 | 47 | 115/466 (24.68%) | 43/47 | 1 | 0/0 | 0 |
| conv3 P2 | 48 | 112/466 (24.03%) | 45/48 | 1 | 0/0 | 0 |
| conv3 B3 | 47 | 107/466 (22.96%) | 43/47 | 2 | 0/0 | 0 |
| conv4 B0 | 34 | 81/470 (17.23%) | 30/34 | 4 | 0/0 | 0 |
| conv4 P1 | 32 | 70/470 (14.89%) | 23/32 | 8 | 0/0 | 0 |
| conv4 P2 | 33 | 82/470 (17.45%) | 25/33 | 7 | 0/0 | 0 |
| conv4 B3 | 35 | 81/470 (17.23%) | 33/35 | 2 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | 1.997 / 2.720 | 0.663 / 1.359 | 1.503 / 1.914 | 3.079 / 4.337 | 1.159 / 1.909 |
| conv2 P1 | 1.895 / 2.770 | 0.666 / 1.369 | 1.514 / 1.884 | 3.047 / 4.462 | 1.164 / 1.982 |
| conv2 P2 | 1.925 / 2.781 | 0.697 / 1.337 | 1.494 / 1.809 | 3.091 / 3.961 | 1.162 / 1.993 |
| conv2 B3 | 1.945 / 2.634 | 0.682 / 1.369 | 1.507 / 1.919 | 3.107 / 4.352 | 1.116 / 1.825 |
| conv3 B0 | 1.927 / 2.390 | 0.647 / 1.108 | 1.504 / 2.061 | 3.174 / 4.212 | 1.179 / 1.938 |
| conv3 P1 | 1.973 / 2.246 | 0.644 / 1.112 | 1.522 / 1.877 | 3.185 / 4.248 | 1.173 / 1.832 |
| conv3 P2 | 1.913 / 2.410 | 0.646 / 1.103 | 1.514 / 1.910 | 3.157 / 4.286 | 1.274 / 2.123 |
| conv3 B3 | 1.903 / 2.239 | 0.658 / 1.090 | 1.514 / 2.131 | 3.127 / 4.254 | 1.176 / 2.042 |
| conv4 B0 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| conv4 P1 | 2.483 / 3.150 | 0.827 / 1.469 | 1.723 / 2.611 | 4.104 / 6.788 | 1.545 / 3.637 |
| conv4 P2 | 2.408 / 3.168 | 0.809 / 1.428 | 1.594 / 2.431 | 3.936 / 6.770 | 1.707 / 3.301 |
| conv4 B3 | 2.325 / 3.230 | 0.747 / 1.403 | 1.732 / 2.780 | 3.887 / 6.828 | 1.709 / 3.596 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | (1, 10] | 0.761 | (1000, 2000] | 7.063 | 7.111 |
| conv2 P1 | (1, 10] | 0.838 | (1000, 2000] | 6.786 | 6.838 |
| conv2 P2 | (1, 10] | 1.584 | (1000, 2000] | 6.876 | 6.929 |
| conv2 B3 | (1, 10] | 3.762 | (1000, 2000] | 6.943 | 6.996 |
| conv3 B0 | (10, 50] | 2.705 | (2000, 4000] | 5.933 | 5.975 |
| conv3 P1 | (1, 10] | 1.845 | (2000, 4000] | 5.171 | 5.225 |
| conv3 P2 | (1, 10] | 1.645 | (2000, 4000] | 5.945 | 5.999 |
| conv3 B3 | (1, 10] | 1.625 | (2000, 4000] | 5.370 | 5.417 |
| conv4 B0 | (10, 50] | 8.589 | (1000, 2000] | 7.185 | 9.435 |
| conv4 P1 | (1, 10] | 1.656 | (1000, 2000] | 7.032 | 7.068 |
| conv4 P2 | (1, 10] | 0.071 | (1000, 2000] | 7.141 | 7.194 |
| conv4 B3 | (1, 10] | 3.299 | (1000, 2000] | 7.104 | 7.151 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 9,728,000 / 88.723 | 5,701,440 / 113.403 | 12,092,096 / 218.231 | 1 | 0 | 0 | 0 / 0 |
| conv2 P1 | 3,400,960 / 27.528 | 5,714,560 / 113.558 | 12,272,832 / 222.436 | 1 | 4 | 0 | 0 / 0 |
| conv2 P2 | 3,381,248 / 27.331 | 5,716,800 / 114.530 | 12,328,448 / 222.084 | 1 | 9 | 0 | 0 / 0 |
| conv2 B3 | 9,728,000 / 87.840 | 5,701,440 / 117.216 | 12,171,008 / 216.497 | 1 | 0 | 0 | 0 / 0 |
| conv3 B0 | 12,800,000 / 118.515 | 5,876,160 / 113.931 | 11,054,016 / 203.898 | 1 | 0 | 0 | 0 / 0 |
| conv3 P1 | 3,827,456 / 31.302 | 5,894,080 / 117.035 | 10,848,832 / 203.246 | 1 | 0 | 0 | 0 / 0 |
| conv3 P2 | 3,871,744 / 31.664 | 5,933,440 / 117.347 | 11,372,608 / 209.142 | 1 | 0 | 0 | 0 / 0 |
| conv3 B3 | 12,800,000 / 121.211 | 5,874,240 / 116.306 | 11,394,048 / 210.402 | 1 | 0 | 0 | 0 / 0 |
| conv4 B0 | 8,704,000 / 81.937 | 5,870,400 / 119.239 | 13,646,272 / 260.367 | 1 | 0 | 3 | 0 / 0 |
| conv4 P1 | 3,314,944 / 26.994 | 5,841,600 / 119.765 | 13,910,784 / 262.764 | 1 | 0 | 1 | 0 / 0 |
| conv4 P2 | 3,346,176 / 27.192 | 5,840,000 / 118.690 | 13,993,216 / 262.998 | 1 | 0 | 1 | 0 / 0 |
| conv4 B3 | 8,960,000 / 83.592 | 5,877,760 / 116.338 | 13,301,248 / 250.012 | 1 | 0 | 1 | 0 / 0 |

## Model-local SDK: bounded conv4 follow-up

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv4 B0 | 34 | 77/470 (16.38%) | 32/34 | 2 | 0/0 | 0 |
| conv4 P1 | 34 | 78/470 (16.60%) | 30/34 | 4 | 0/0 | 0 |
| conv4 P2 | 34 | 72/470 (15.32%) | 32/34 | 2 | 0/0 | 0 |
| conv4 B3 | 34 | 74/470 (15.74%) | 26/33 | 7 | 1/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv4 B0 | 2.367 / 3.265 | 0.809 / 1.387 | 1.600 / 2.750 | 3.978 / 6.857 | 1.769 / 3.533 |
| conv4 P1 | 2.370 / 3.315 | 0.793 / 1.388 | 1.673 / 2.854 | 3.987 / 6.735 | 1.646 / 3.510 |
| conv4 P2 | 2.382 / 3.307 | 0.773 / 1.425 | 1.554 / 2.721 | 3.989 / 6.844 | 1.793 / 3.662 |
| conv4 B3 | 2.413 / 3.410 | 0.822 / 1.470 | 1.863 / 2.810 | 4.070 / 7.237 | 1.834 / 3.653 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv4 B0 | (1, 10] | 0.109 | (1000, 2000] | 7.206 | 7.248 |
| conv4 P1 | (1, 10] | 9.639 | (1000, 2000] | 7.544 | 10.107 |
| conv4 P2 | (1, 10] | 6.141 | (1000, 2000] | 6.925 | 6.980 |
| conv4 B3 | (1, 10] | 1.147 | (1000, 2000] | 10.464 | 10.497 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv4 B0 | 8,704,000 / 80.465 | 5,868,160 / 116.477 | 13,635,456 / 254.978 | 1 | 0 | 2 | 0 / 0 |
| conv4 P1 | 3,357,440 / 28.328 | 5,891,520 / 120.284 | 13,370,816 / 253.022 | 1 | 0 | 0 | 0 / 0 |
| conv4 P2 | 3,384,832 / 28.697 | 5,936,320 / 117.485 | 13,719,680 / 256.229 | 1 | 0 | 1 | 0 / 0 |
| conv4 B3 | 8,704,000 / 81.563 | 5,947,840 / 118.105 | 13,344,768 / 250.756 | 1 | 0 | 2 | 0 / 0 |

## Model-local SDK: x2f clearing

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 38 | 82/499 (16.43%) | 28/38 | 1 | 0/0 | 0 |
| conv2 P1 | 38 | 72/499 (14.43%) | 28/38 | 1 | 0/0 | 0 |
| conv2 P2 | 38 | 76/499 (15.23%) | 29/38 | 1 | 0/0 | 0 |
| conv2 B3 | 39 | 78/499 (15.63%) | 30/39 | 1 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | 1.909 / 2.731 | 0.608 / 1.089 | 1.488 / 1.577 | 3.112 / 4.237 | 1.164 / 2.020 |
| conv2 P1 | 1.938 / 2.789 | 0.622 / 1.087 | 1.494 / 1.760 | 3.114 / 4.468 | 1.120 / 2.231 |
| conv2 P2 | 1.947 / 2.642 | 0.605 / 1.089 | 1.493 / 1.660 | 3.167 / 4.342 | 1.162 / 2.443 |
| conv2 B3 | 1.933 / 2.683 | 0.630 / 1.093 | 1.516 / 1.791 | 3.131 / 4.141 | 1.166 / 1.817 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv2 B0 | (1, 10] | 0.690 | (1000, 2000] | 6.976 | 7.035 |
| conv2 P1 | (1, 10] | 2.510 | (1000, 2000] | 6.912 | 6.947 |
| conv2 P2 | (1, 10] | 3.096 | (1000, 2000] | 7.015 | 7.062 |
| conv2 B3 | (50, 100] | 2.937 | (1000, 2000] | 6.921 | 6.969 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv2 B0 | 9,728,000 / 88.112 | 5,701,120 / 109.779 | 9,467,648 / 178.266 | 1 | 0 | 0 | 0 / 0 |
| conv2 P1 | 4,185,856 / 34.800 | 5,717,440 / 112.970 | 9,246,080 / 173.395 | 1 | 0 | 0 | 0 / 0 |
| conv2 P2 | 4,175,360 / 34.674 | 5,710,080 / 109.968 | 9,508,352 / 175.622 | 1 | 24 | 0 | 0 / 0 |
| conv2 B3 | 9,984,000 / 90.293 | 5,708,160 / 111.281 | 9,137,216 / 168.967 | 1 | 0 | 0 | 0 / 0 |

## Model-local SDK: probe overhead

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv2 On0 | 38 | 81/499 (16.23%) | 28/38 | 1 | 0/0 | 0 |
| conv2 Off1 | 38 | 86/499 (17.23%) | Unmeasured | 1 | Unmeasured | Unmeasured |
| conv2 Off2 | 38 | 71/499 (14.23%) | Unmeasured | 1 | Unmeasured | Unmeasured |
| conv2 On3 | 38 | 90/499 (18.04%) | 29/38 | 1 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv2 On0 | 1.910 / 2.723 | 0.704 / 1.336 | 1.494 / 1.769 | 3.089 / 4.443 | 1.163 / 1.790 |
| conv2 Off1 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| conv2 Off2 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| conv2 On3 | 1.932 / 2.699 | 0.689 / 1.339 | 1.479 / 2.106 | 3.101 / 4.414 | 1.165 / 1.920 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv2 On0 | (1, 10] | 0.567 | (1000, 2000] | 6.721 | 6.777 |
| conv2 Off1 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| conv2 Off2 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| conv2 On3 | (1, 10] | 1.645 | (1000, 2000] | 7.371 | 7.429 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv2 On0 | 3,370,240 / 27.291 | 5,706,880 / 113.379 | 12,155,968 / 217.610 | 1 | 0 | 1 | 0 / 0 |
| conv2 Off1 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured / 0 |
| conv2 Off2 | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured / 0 |
| conv2 On3 | 3,407,104 / 27.598 | 5,710,720 / 114.219 | 12,354,304 / 224.306 | 1 | 28 | 0 | 0 / 0 |

## Model-local SDK: speaker load

| Run | Captions | WER edits / words (%) | Speaker correct / eligible | Unknown or missing | Excluded mixed / no reference | Captions outside playback |
|---|---:|---:|---:|---:|---:|---:|
| conv2 On0 | 38 | 78/499 (15.63%) | 29/38 | 1 | 0/0 | 0 |
| conv2 Off1 | 38 | 81/499 (16.23%) | Disabled | 38 intentional | Unmeasured | 0 |
| conv2 Off2 | 38 | 77/499 (15.43%) | Disabled | 38 intentional | Unmeasured | 0 |
| conv2 On3 | 38 | 74/499 (14.83%) | 28/38 | 2 | 0/0 | 0 |

| Run | Final publication | Draft freshness | First draft from start | Speaker publication | Label after caption |
|---|---:|---:|---:|---:|---:|
| conv2 On0 | 1.969 / 2.664 | 0.677 / 1.335 | 1.512 / 1.719 | 3.078 / 4.463 | 1.156 / 2.019 |
| conv2 Off1 | 1.931 / 2.734 | 0.678 / 1.328 | 1.467 / 1.796 | Disabled | Disabled |
| conv2 Off2 | 1.896 / 2.792 | 0.685 / 1.334 | 1.486 / 2.148 | Disabled | Disabled |
| conv2 On3 | 1.945 / 2.699 | 0.690 / 1.347 | 1.519 / 2.149 | 3.079 / 4.072 | 1.164 / 2.048 |

| Run | Wait p99 bucket (µs) | Wait max (ms) | Push hold p99 bucket (µs) | Push hold max (ms) | Read-to-push max (ms) |
|---|---:|---:|---:|---:|---:|
| conv2 On0 | (1, 10] | 2.631 | (1000, 2000] | 8.565 | 8.601 |
| conv2 Off1 | (1, 10] | 4.983 | (1000, 2000] | 7.568 | 7.582 |
| conv2 Off2 | (1, 10] | 2.290 | (1000, 2000] | 8.846 | 8.868 |
| conv2 On3 | (1, 10] | 1.309 | (1000, 2000] | 7.086 | 7.139 |

| Run | Clear bytes / ms | Queue copy bytes / ms | Snapshot copy bytes / ms | Ready high water | Cache unavailable checks | Feature fallbacks | DMA overflow / phrase drops |
|---|---:|---:|---:|---:|---:|---:|---:|
| conv2 On0 | 3,345,408 / 27.014 | 5,703,360 / 116.100 | 12,173,952 / 221.022 | 1 | 0 | 1 | 0 / 0 |
| conv2 Off1 | 3,398,912 / 28.899 | 5,700,480 / 116.643 | 12,133,824 / 206.255 | 1 | 0 | 0 | 0 / 0 |
| conv2 Off2 | 3,375,872 / 28.722 | 5,715,200 / 116.162 | 12,260,160 / 208.753 | 1 | 0 | 1 | 0 / 0 |
| conv2 On3 | 3,409,152 / 28.715 | 5,719,680 / 115.151 | 12,265,344 / 221.969 | 1 | 5 | 0 | 0 / 0 |

## Interpretation

Keep original and model-local SDK cohorts separate. The original conv3 concern
did not repeat in its bounded follow-up; the new primary conv4 concern did not
repeat in its one bounded follow-up, but the original holds are retained. The
x2f clearing bracket raises a label-after-caption p90 flag. Clearing work falls
substantially without an established caption-speed gain. Probe and speaker-load
controls are not additional speaker algorithms. See the results document for
gate decisions, exact-input evidence, numerical-fixture failures and limitations.
