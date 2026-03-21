"""Tests for price service (app/services/price_service.py)."""
from unittest.mock import MagicMock, patch
from app.services.price_service import PriceService


def _mock_cache(stored=None):
    """Return a mock cache object backed by a simple dict."""
    store = stored if stored is not None else {}
    c = MagicMock()
    c.get.side_effect = lambda key: store.get(key)
    c.set.side_effect = lambda key, value, timeout=None: store.update({key: value})
    return c


class TestPriceServiceGetPriceUsd:
    """Test PriceService.get_price_usd() method."""

    def test_get_price_usd_success(self):
        """get_price_usd should return price for valid asset."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'bitcoin': {'usd': 45000}}
            mock_get.return_value.raise_for_status = MagicMock()

            price = PriceService.get_price_usd('BTC')
            assert price == 45000

    def test_get_price_usd_invalid_asset(self):
        """get_price_usd should raise ValueError for invalid asset."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch.object(PriceService, '_resolve_id', return_value=None):
            try:
                PriceService.get_price_usd('INVALID')
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unknown symbol" in str(e)

    def test_get_price_usd_api_error(self):
        """get_price_usd should raise exception on API error."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")

            try:
                PriceService.get_price_usd('TESTCOIN123')
                assert False, "Should have raised exception"
            except Exception as e:
                assert "API Error" in str(e) or "Unknown symbol" in str(e)

    def test_get_price_usd_caching(self):
        """get_price_usd should return cached result on second call."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'bitcoin': {'usd': 45000}}
            mock_get.return_value.raise_for_status = MagicMock()

            price1 = PriceService.get_price_usd('BTC')
            price2 = PriceService.get_price_usd('BTC')

            assert price1 == price2
            assert mock_get.call_count == 1

    def test_get_price_usd_force_refresh(self):
        """get_price_usd should bypass cache with force_refresh=True."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'bitcoin': {'usd': 45000}}
            mock_get.return_value.raise_for_status = MagicMock()

            price1 = PriceService.get_price_usd('BTC')
            price2 = PriceService.get_price_usd('BTC', force_refresh=True)

            assert price1 == price2
            assert mock_get.call_count >= 2


class TestPriceServiceGetPricesBatch:
    """Test PriceService.get_prices_usd_batch() method."""

    def test_get_prices_batch_success(self):
        """get_prices_usd_batch should return prices for multiple assets."""
        mock_cache = _mock_cache()
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'bitcoin': {'usd': 45000},
                'ethereum': {'usd': 3000},
            }
            mock_get.return_value.raise_for_status = MagicMock()

            prices = PriceService.get_prices_usd_batch(['BTC', 'ETH'])
            assert prices.get('BTC') == 45000
            assert prices.get('ETH') == 3000

    def test_get_prices_batch_empty(self):
        """get_prices_usd_batch should return empty dict for empty input."""
        prices = PriceService.get_prices_usd_batch([])
        assert prices == {}

    def test_get_prices_batch_uses_cache(self):
        """get_prices_usd_batch should not fetch symbols already in cache."""
        mock_cache = _mock_cache(stored={"price_usd_BTC": 45000.0})
        with patch.object(PriceService, '_cache', return_value=mock_cache), \
             patch('app.services.price_service.requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'ethereum': {'usd': 3000}}
            mock_get.return_value.raise_for_status = MagicMock()

            prices = PriceService.get_prices_usd_batch(['BTC', 'ETH'])
            assert prices.get('BTC') == 45000.0
            assert prices.get('ETH') == 3000
            # BTC was cached, so only one API call for ETH
            assert mock_get.call_count == 1
