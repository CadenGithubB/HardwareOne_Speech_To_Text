// Experimental address walk with matched diagnostic selector/counters.
static bool conv_loop_pie_tiled(ConvArgsType &args,
                                conv_pie_fn_t body,
                                int feat_bytes,
                                int filt_bytes,
                                void *input_ptr,
                                void *output_ptr,
                                int height,
                                int width)
{
#if CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32S31
    constexpr int filter_bytes = 16 * 1024;
    constexpr int spatial_tile = 32;
#else
    // HardwareOne: pointwise tiles sized for the ESP32-P4's 64 KB 2-way L1D,
    // which both HP cores share. The shipped 32 KB filter tile x 32-pixel
    // spatial tile per core is 2 x (32 + 16) = 96 KB. Here: 16 KB filter
    // tile (int8, C_in 512: 32-channel tiles), 64-pixel spatial tile: on the
    // 15x5 the fastest tile measured once the single-column depthwise layers
    // split by channel halves (dl_base_conv_args.hpp).
    // Bit-exact: each body() call still reduces one pixel over all input
    // channels in the same order; only the order of (pixel, channel-tile)
    // calls changes.
    constexpr int filter_bytes = 16 * 1024;
    constexpr int spatial_tile = 64;
#endif

    // height/width/pointers are the body rectangle: the full map when there is
    // no pad, or conv_1x1_body_view() after 1x1 pad fill. Stride is already in
    // input_stride_*_offset; do not require stride==1 or reject padding.
    if (!body || !conv_is_1x1(args) || feat_bytes <= 0 || filt_bytes <= 0 || args.input_channel <= 0 || width <= 0 ||
        height <= 0) {
        return false;
    }
    const int lanes = 16 / feat_bytes;
    if (lanes <= 0 || args.input_channel < lanes || args.input_channel % lanes || args.output_channel % lanes ||
        args.c_remainder || args.n_remainder) {
        return false;
    }
    if ((reinterpret_cast<uintptr_t>(input_ptr) & 15) || (reinterpret_cast<uintptr_t>(output_ptr) & 15)) {
        return false;
    }
    if (args.activation_type != Linear && args.activation_type != ReLU) {
        return false;
    }
#if CONFIG_IDF_TARGET_ESP32S3
    if (args.mac_shift < 0) {
        return false;
    }
#endif

    const int channel_tile = (filter_bytes / filt_bytes / args.input_channel) / lanes * lanes;
    const int pixels = height * width;
    if (channel_tile < lanes || args.output_channel < 2 * channel_tile || pixels < 2) {
        return false;
    }

    const bool pointwise_scan = hw1_pointwise_scan.load(std::memory_order_relaxed) != 0;
    hw1_pointwise_calls.fetch_add(1, std::memory_order_relaxed);
    if (width == 1) hw1_pointwise_width1.fetch_add(1, std::memory_order_relaxed);
    if (args.input_channel == 512 && args.output_channel == 512)
        hw1_pointwise_512.fetch_add(1, std::memory_order_relaxed);
    const int bias_bytes = (feat_bytes == 1) ? (int)sizeof(int32_t) : (int)sizeof(int64_t);
    const bool per_channel = args.mac_shift == INT_MIN;
    for (int begin = 0; begin < pixels; begin += spatial_tile) {
        const int end = std::min(pixels, begin + spatial_tile);
        for (int channel = 0; channel < args.output_channel; channel += channel_tile) {
            ConvArgsType tile = args;
            tile.output_channel = std::min(channel_tile, args.output_channel - channel);
            tile.n_div_x = tile.output_channel / lanes;
            tile.filter_element = conv_ptr_add(args.filter_element, channel * args.input_channel, filt_bytes);
            if (args.bias_element) {
                tile.bias_element = conv_ptr_add(args.bias_element, channel, bias_bytes);
            }
            if (per_channel && args.tie_filter_channel_factor) {
                tile.tie_filter_channel_factor = conv_ptr_add(args.tie_filter_channel_factor, channel, feat_bytes);
            }
            if (width == 1 && pointwise_scan) {
                // Same pixel/channel-tile order and kernel arguments. A single
                // column advances by row stride; no per-pixel division or
                // repeated multiplication is needed. Avoid forming a pointer
                // beyond the last body element after the final call.
                void *in = conv_ptr_add(input_ptr, begin * args.input_stride_y_offset, feat_bytes);
                void *out = conv_ptr_add(output_ptr, begin * args.output_y_offset + channel, feat_bytes);
                for (int pixel = begin; pixel < end; ++pixel) {
                    body(out, in, (void *)&tile);
                    if (pixel + 1 < end) {
                        in = conv_ptr_add(in, args.input_stride_y_offset, feat_bytes);
                        out = conv_ptr_add(out, args.output_y_offset, feat_bytes);
                    }
                }
            } else {
                for (int pixel = begin; pixel < end; ++pixel) {
                    const int y = pixel / width;
                    const int x = pixel % width;
                    void *in = conv_ptr_add(
                        input_ptr, y * args.input_stride_y_offset + x * args.input_stride_x_offset, feat_bytes);
                    void *out =
                        conv_ptr_add(output_ptr, y * args.output_y_offset + x * args.output_x_offset + channel, feat_bytes);
                    body(out, in, (void *)&tile);
                }
            }
        }
    }
    return true;
}
