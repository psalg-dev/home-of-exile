"""
Direct test of the LLM explainer service — no HTTP server, no LuaJIT needed.

Calls generate_explanation() directly with a sample Necromancer upgrade
and prints the source ('llm' or 'template') and the explanation text.
"""
import asyncio


def main() -> None:
    from app.services.llm_explainer import get_llm_service

    svc = get_llm_service()
    print(f"api_key set:      {bool(svc._api_key)}")
    print(f"client ready:     {svc._client is not None}")
    print(f"llm_enabled:      {svc.llm_enabled}")
    print(f"_should_use_llm:  {svc._should_use_llm()}")
    print()

    async def run() -> None:
        svc.timeout_seconds = 15.0  # increase timeout for test (default 3s may be too tight)
        text, source = await svc.generate_explanation(
            slot="Helmet",
            current_item="Iron Hat",
            suggested_item="Starkonja's Head",
            category="power_upgrade",
            deltas={"dps": 250_000.0, "life": 300.0},
            price_divine=2.5,
            level=78,
            ascendancy="Necromancer",
            damage_type="physical",
            playstyle="summoner",
            main_skill="Raise Spectre",
            template_explanation=(
                "Starkonja's Head in your Helmet adds +250,000 DPS and +300 EHP."
            ),
        )
        print(f"Source:      {source}")
        print(f"Explanation: {text}")
        t = svc._tracker
        print(f"Tokens:      input={t.total_input_tokens}  output={t.total_output_tokens}")
        print(f"Cost USD:    {t.estimated_cost_usd:.5f}")

    asyncio.run(run())


main()
