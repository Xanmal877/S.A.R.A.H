from modules.personalityModule import PersonalityModule


class PersonaMapper:
    """
    Translates numerical personality traits from a PersonalityModule
    into descriptive text for LLM prompting.
    """

    def map_traits(self, personality_module: PersonalityModule) -> str:
        """
        Maps numerical personality traits to a cohesive descriptive paragraph.
        """

        # Mapping definitions
        mappings = {
            "energy": {
                (0, 30): "introverted, reserved",
                (31, 70): "balanced",
                (71, 100): "extraverted, energetic"
            },
            "mind": {
                (0, 30): "focused on concrete facts and details",
                (31, 70): "balanced",
                (71, 100): "intuitive, focused on patterns and possibilities"
            },
            "nature": {
                (0, 30): "logical, objective",
                (31, 70): "balanced",
                (71, 100): "empathetic, value-driven"
            },
            "tactics": {
                (0, 30): "organized, decisive",
                (31, 70): "balanced",
                (71, 100): "spontaneous, flexible"
            },
            "identity": {
                (0, 30): "self-critical, cautious",
                (31, 70): "balanced",
                (71, 100): "confident, assertive"
            }
        }

        traits_descriptions = []

        # Order of traits to maintain a consistent paragraph flow
        trait_order = ["energy", "mind", "nature", "tactics", "identity"]

        for trait in trait_order:
            value = getattr(personality_module, trait)
            description = "balanced" # Default

            for (low, high), text in mappings[trait].items():
                if low <= value <= high:
                    description = text
                    break

            traits_descriptions.append(description)

        # Construct a cohesive paragraph
        if not traits_descriptions:
            return "The agent's psyche is currently undefined."

        if len(traits_descriptions) == 1:
            return f"The agent is {traits_descriptions[0]}."

        # Join all but the last with commas, then add the last one with 'and'
        main_desc = ", ".join(traits_descriptions[:-1])
        final_desc = traits_descriptions[-1]

        return f"The agent is {main_desc}, and {final_desc}."
