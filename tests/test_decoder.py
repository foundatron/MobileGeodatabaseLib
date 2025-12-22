"""Tests for ST_Geometry decoder."""

import pytest

from mobile_geodatabase import (
    CoordinateSystem,
    STGeometryDecoder,
    decode_geometry,
)


class TestSTGeometryDecoder:
    def test_decoder_init_default(self):
        decoder = STGeometryDecoder()
        assert decoder.cs.x_origin == -20037700
        assert decoder.cs.effective_xy_scale == 20000

    def test_decoder_init_custom(self):
        cs = CoordinateSystem(x_origin=0, y_origin=0, xy_scale=5000)
        decoder = STGeometryDecoder(cs)
        assert decoder.cs.x_origin == 0
        assert decoder.cs.effective_xy_scale == 10000

    def test_magic_header(self):
        decoder = STGeometryDecoder()
        assert bytes([0x64, 0x11, 0x0F, 0x00]) == decoder.MAGIC

    def test_coord_threshold(self):
        decoder = STGeometryDecoder()
        assert decoder.COORD_THRESHOLD == 100_000_000_000

    def test_zigzag_decode(self):
        decoder = STGeometryDecoder()
        # Zigzag encoding: 0->0, 1->-1, 2->1, 3->-2, 4->2, etc.
        assert decoder.zigzag_decode(0) == 0
        assert decoder.zigzag_decode(1) == -1
        assert decoder.zigzag_decode(2) == 1
        assert decoder.zigzag_decode(3) == -2
        assert decoder.zigzag_decode(4) == 2

    def test_read_varint(self):
        decoder = STGeometryDecoder()
        # Single byte varint (< 128)
        data = bytes([0x05])
        value, offset = decoder.read_varint(data, 0)
        assert value == 5
        assert offset == 1

        # Multi-byte varint
        # 300 = 0b100101100 = 0xAC 0x02
        data = bytes([0xAC, 0x02])
        value, offset = decoder.read_varint(data, 0)
        assert value == 300
        assert offset == 2

    def test_decode_invalid_magic(self):
        decoder = STGeometryDecoder()
        blob = bytes([0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
        with pytest.raises(ValueError, match="Invalid magic header"):
            decoder.decode(blob)

    def test_decode_too_short(self):
        decoder = STGeometryDecoder()
        blob = bytes([0x64, 0x11, 0x0F])  # Only 3 bytes
        with pytest.raises(ValueError, match="too short"):
            decoder.decode(blob)

    def test_decode_empty_geometry(self):
        decoder = STGeometryDecoder()
        # Valid header but 0 points
        blob = bytes([0x64, 0x11, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00])
        with pytest.raises(ValueError, match="Empty geometry"):
            decoder.decode(blob)


class TestDecodeGeometry:
    def test_decode_with_defaults(self):
        # This tests the convenience function
        # We can't fully test without a real blob, but we can test error handling
        with pytest.raises(ValueError):
            decode_geometry(bytes([0x00, 0x00, 0x00, 0x00]))

    def test_decode_with_custom_params(self):
        with pytest.raises(ValueError):
            decode_geometry(
                bytes([0x00, 0x00, 0x00, 0x00]), x_origin=0, y_origin=0, xy_scale=1000
            )


class TestRawToCoord:
    def test_raw_to_coord_default(self):
        """Test coordinate conversion with default coordinate system"""
        decoder = STGeometryDecoder()
        # With default CS: x_origin=-20037700, y_origin=-30241100, effective_scale=20000
        # If raw_x = 137695015937, then:
        # x = 137695015937 / 20000 + (-20037700) = 6884750.79685 - 20037700 = -13152949.20315
        raw_x = 137695015937
        raw_y = 724105586082

        x, y = decoder.raw_to_coord(raw_x, raw_y)

        # Should be in Washington State range for EPSG:3857
        assert -14_000_000 < x < -12_000_000
        assert 5_500_000 < y < 6_500_000
