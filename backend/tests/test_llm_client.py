from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import APIError, APITimeoutError, AuthenticationError, RateLimitError

from app.services.llm import BudgetExceededError, LLMClient, TokenBudget


class TestTokenBudget:
    def test_within_limit(self):
        budget = TokenBudget(max_tokens_per_call=4096)
        budget.record(2000)
        assert not budget.exceeded

    def test_exceeded(self):
        budget = TokenBudget(max_tokens_per_call=4096)
        budget.record(5000)
        assert not budget.exceeded
        assert budget.would_exceed_call(5000)

    def test_accumulation(self):
        budget = TokenBudget(max_tokens_per_call=4096)
        budget.record(3000)
        budget.record(2000)
        assert not budget.exceeded
        assert budget.total_tokens == 5000

    def test_reset(self):
        budget = TokenBudget(max_tokens_per_call=4096)
        budget.record(3000)
        budget.reset()
        assert budget.total_tokens == 0
        assert not budget.exceeded

    def test_call_count(self):
        budget = TokenBudget(max_tokens_per_call=4096)
        budget.record(100)
        budget.record(200)
        assert budget.total_tokens == 300
        assert budget.call_count == 2


class TestLLMClient:
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_then_succeed(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash")
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "hello"
        mock_response.usage = AsyncMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        mock_create = AsyncMock(
            side_effect=[
                RateLimitError("rate limited", response=AsyncMock(status_code=429), body={}),
                RateLimitError("rate limited", response=AsyncMock(status_code=429), body={}),
                mock_response,
            ]
        )

        with patch.object(client.client.chat.completions, "create", mock_create):
            result = await client.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
                estimated_tokens=15,
            )
            assert result == "hello"
            assert mock_create.call_count == 3
            assert client.total_tokens == 15

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash")

        mock_create = AsyncMock(side_effect=APITimeoutError("timeout"))

        with patch.object(client.client.chat.completions, "create", mock_create):
            with pytest.raises(APITimeoutError):
                await client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    estimated_tokens=15,
                )
            assert mock_create.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash")

        mock_create = AsyncMock(
            side_effect=AuthenticationError(
                "auth failed", response=AsyncMock(status_code=401), body={}
            )
        )

        with patch.object(client.client.chat.completions, "create", mock_create):
            with pytest.raises(AuthenticationError):
                await client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    estimated_tokens=15,
                )
            assert mock_create.call_count == 1

    @pytest.mark.asyncio
    async def test_budget_pre_check_blocks(self):
        budget = TokenBudget(max_tokens_per_call=100)
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash", budget=budget)

        with pytest.raises(BudgetExceededError):
            await client.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                estimated_tokens=101,
            )

    @pytest.mark.asyncio
    async def test_budget_does_not_block_on_accumulated_usage(self):
        budget = TokenBudget(max_tokens_per_call=100)
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash", budget=budget)
        budget.record(150)

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage = None

        mock_create = AsyncMock(return_value=mock_response)
        with patch.object(client.client.chat.completions, "create", mock_create):
            result = await client.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                estimated_tokens=20,
            )
            assert result == "ok"

    @pytest.mark.asyncio
    async def test_estimated_tokens_defaults_to_message_length(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash")

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage = None

        mock_create = AsyncMock(return_value=mock_response)
        with patch.object(client.client.chat.completions, "create", mock_create):
            result = await client.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
            )
            assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_budget_no_estimated_tokens_required(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash", budget=None)

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage = None

        mock_create = AsyncMock(return_value=mock_response)
        with patch.object(client.client.chat.completions, "create", mock_create):
            result = await client.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
            )
            assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_api_error(self):
        client = LLMClient(api_key="sk-test", model="deepseek-v4-flash")

        mock_create = AsyncMock(
            side_effect=APIError(
                "bad request",
                request=httpx.Request(
                    "POST", "https://api.deepseek.com/v1/chat/completions"
                ),
                body={},
            )
        )

        with patch.object(client.client.chat.completions, "create", mock_create):
            with pytest.raises(APIError):
                await client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    estimated_tokens=15,
                )
            assert mock_create.call_count == 1
