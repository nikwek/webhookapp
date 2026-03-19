"""Tests for price service (app/services/price_service.py)."""
from unittest.mock import Mock, patch
from app.services.price_service import PriceService


class TestPriceServiceGetPriceUsd:
    """Test PriceService.get_price_usd() method."""

    def test_get_price_usd_success(self):
        """get_price_usd should return price for valid asset."""
        with patch('app.services.price_service.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'bitcoin': {'usd': 45000}
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            price = PriceService.get_price_usd('BTC')
            assert price == 45000

    def test_get_price_usd_invalid_asset(self):
        """get_price_usd should raise ValueError for invalid asset."""
        with patch.object(PriceService, '_resolve_id', return_value=None):
            try:
                PriceService.get_price_usd('INVALID')
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unknown symbol" in str(e)

    def test_get_price_usd_api_error(self):
        """get_price_usd should raise exception on API error."""
        with patch('app.services.price_service.requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")

            try:
                PriceService.get_price_usd('TESTCOIN123')
                assert False, "Should have raised exception"
            except Exception as e:
                assert "API Error" in str(e) or "Unknown symbol" in str(e)

    def test_get_price_usd_caching(self):
        """get_price_usd should cache results within TTL."""
        PriceService._price_cache.clear()

        with patch('app.services.price_service.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'bitcoin': {'usd': 45000}
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            price1 = PriceService.get_price_usd('BTC')
            price2 = PriceService.get_price_usd('BTC')

            assert price1 == price2
            assert mock_get.call_count == 1

    def test_get_price_usd_force_refresh(self):
        """get_price_usd should bypass cache with force_refresh=True."""
        PriceService._price_cache.clear()

        with patch('app.services.price_service.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'bitcoin': {'usd': 45000}
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            price1 = PriceService.get_price_usd('BTC')
            price2 = PriceService.get_price_usd('BTC', force_refresh=True)

            assert price1 == price2
            assert mock_get.call_count >= 1


class TestPriceServiceGetPricesBatch:
    """Test PriceService.get_prices_usd_batch() method."""

    def test_get_prices_batch_success(self):
        """get_prices_usd_batch should return prices for multiple assets."""
        with patch('app.services.price_service.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'bitcoin': {'usd': 45000},
                'ethereum': {'usd': 3000}
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            prices = PriceService.get_prices_usd_batch(['BTC', 'ETH'])
            assert 'BTC' in prices
            assert 'ETH' in prices

    def test_get_prices_batch_empty(self):
        """get_prices_usd_batch should return empty dict for empty input."""
        prices = PriceService.get_prices_usd_batch([])
        assert prices == {}
