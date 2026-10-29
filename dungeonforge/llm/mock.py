import random
import re
from typing import List, Dict, Any
from dungeonforge.llm.base import BaseLLMClient, LLMResponse


class MockLLMClient(BaseLLMClient):
    """Offline local narrative engine for zero-configuration testing and play."""

    HIT_TEMPLATES = [
        "Your blow lands with decisive force! Steel bites into armor, carving a deep furrow as your foe recoils with a guttural roar. {dmg_desc}",
        "Moving with practiced precision, your strike slips past their guard. Blood splatters across the cobblestones as you pivot into an advantageous stance. {dmg_desc}",
        "A devastating strike! You exploit an opening in their defense, sending shockwaves through their frame as they stagger backward. {dmg_desc}"
    ]

    MISS_TEMPLATES = [
        "You press the attack, but their shield rises just in time to deflect the blow with a ringing clang. Sparks scatter into the gloom.",
        "Your blade cuts through the empty air as your opponent sidesteps with eerie grace, their mocking laughter echoing through the hall.",
        "The strike glances harmlessly off heavy iron plating. Your foe counters with a fierce glare, preparing their retaliation."
    ]

    STORY_TEMPLATES = [
        "The chilling mists of Barovia swirl about your boots. From the canopy of the Svalich Woods, unseen ravens watch your every move with intelligent, glossy eyes.",
        "The ancient iron door groans as you push it ajar. Beyond, shadows lengthen across cracked flagstones, smelling faintly of old parchment and dormant magic.",
        "A sudden gust of wind snuffs out the peripheral torches, plunging the corridor into oppressive twilight. Somewhere in the dark ahead, iron rattles against stone."
    ]

    CAMPAIGN_SCENES = {
        "Minecraft: Lightning Keep": (
            "Rain patters against Lightning Keep's stone battlements. Somewhere inside, six magical lightning rods await discovery; restoring the shield could give the refugees a safe home.",
            "You carry out your action among the keep's weathered stonework, watching for creatures and clues to the missing lightning rods.",
            "Your words echo through Lightning Keep. The plight of the refugees gives every promise weight.",
        ),
        "The Lost Dungeon of Rickedness": (
            "Rick's voice crackles through the dungeon, offering an unsolicited critique of your progress. Another strange chamber waits beyond the next door.",
            "You carry out your action while Rick provides an unhelpful running commentary. The dungeon remains full of questionable design decisions and very real dangers.",
            "Rick pauses just long enough to consider your words before replying with another sarcastic observation about dungeon adventuring.",
        ),
        "Marvel 5e: Superhero Chronicles": (
            "Sirens echo between Manhattan's towers. Civilians hurry behind police lines while the trail of stolen experimental technology waits to be followed.",
            "You carry out your action amid Manhattan's restless streets, keeping the safety of nearby civilians in mind.",
            "Your words cut through Manhattan's noise. The people nearby turn toward you, hoping the situation is finally under control.",
        ),
        "Star Wars: Galactic Rebellion": (
            "A freighter's engines rumble beneath the noise of the spaceport. Imperial patrols are tightening their search, and the Rebel Alliance still needs the encrypted data delivered.",
            "You carry out your action in the bustling spaceport, keeping one eye on the Imperial patrols and another on your route to the freighter.",
            "Your words compete with the hum of repulsorlifts and distant engine noise. Nearby travelers glance toward the Imperial patrol before answering.",
        ),
    }

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> LLMResponse:
        # Find the last user message
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        context = next((m["content"] for m in messages if m["role"] == "user"), "")
        campaign = re.search(r"### ACTIVE CAMPAIGN\n([^\n]+)", context)
        scene = self.CAMPAIGN_SCENES.get(campaign[1].strip()) if campaign else None

        state_updates = {}

        if "[RULE CHECK OUTCOME:" in last_user:
            if "[WEG D6 Rest]" in last_user:
                text = "You pause to recover. Your recorded wound state and remaining resources still determine what you can do next."
            elif "[WEG D6 Check:" in last_user:
                text = "Your approach succeeds. You can act on what you have learned or choose your next move." if "SUCCESS" in last_user else "Your attempt falls short. You can try another approach or reconsider your plan."
                if "complication" in last_user:
                    text += " An unexpected complication also needs the gamemaster's attention."
            elif "HIT" in last_user or "SUCCESS" in last_user:
                tmpl = random.choice(self.HIT_TEMPLATES)
                dmg_desc = "The creature reels from the damage."
                text = tmpl.format(dmg_desc=dmg_desc)
            else:
                text = random.choice(self.MISS_TEMPLATES)
        elif "> You say" in last_user:
            text = scene[2] if scene else (
                "Your words cut through the tense silence. The figures before you exchange cautious glances, "
                "their hands drifting subtly toward their weapons before their leader speaks: "
                "'Few speak so boldly in these shadowed lands, traveler. What is your true business here?'"
            )
        elif "> You" in last_user:
            text = scene[1] if scene else (
                "You carefully carry out your action. The heavy air hangs thick with anticipation as every footstep "
                "kicks up ancient dust. The shadows warp and stretch along the damp stonework, revealing a hidden archway "
                "partially veiled behind rotting tapestries."
            )
        else:
            text = scene[0] if scene else random.choice(self.STORY_TEMPLATES)

        return LLMResponse(
            text=text,
            state_updates=state_updates,
            model="mock-narrator-v1"
        )
