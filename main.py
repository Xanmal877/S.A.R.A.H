from utility_ai import EnhancedLearningUtilityAI

from llm_director import EnhancedExperientialLLMDirector, HAS_OLLAMA



class EnhancedExperientialSarah:

    """Enhanced main learning system"""

    

    def __init__(self):

        print("🚀 Initializing Enhanced Experiential Learning Sarah AI...")

        

        self.utility_ai = EnhancedLearningUtilityAI()

        self.llm_director = EnhancedExperientialLLMDirector()

        

        print("✅ Enhanced Experiential Sarah AI ready!")

        print("🧪 Sarah learns what works through strategic experimentation")

    

    def process_command(self, user_input: str) -> bool:

        """Process user command through enhanced experiential learning"""

        return self.llm_director.process_user_command(user_input, self.utility_ai)

    

    def run_interactive(self):

        """Run interactive mode"""

        print("\n🤖 Enhanced Experiential Learning Sarah AI Ready!")

        print("Sarah learns what works through strategic trial and error")

        print("\nCommands like:")

        print("  'Open YouTube' - Sarah will strategically try browsers")

        print("  'Open Steam' - Sarah will experiment and remember what works")

        print("  'knowledge' - See what Sarah has learned")

        print("  'quit' - exit")

        print("=" * 60)

        

        while True:

            try:

                command = input("\nYou: ").strip()

                

                if not command:

                    continue

                

                if command.lower() in ['quit', 'exit', 'bye']:

                    print("👋 Goodbye!")

                    break

                

                if command.lower() == 'knowledge':

                    knowledge = self.utility_ai.knowledge.get_knowledge_summary()

                    print(f"\n📚 Sarah's Enhanced Knowledge:\n{knowledge}")

                    continue

                

                # Process command

                success = self.process_command(command)

                

                if success:

                    print("\n🎉 Task completed successfully!")

                else:

                    print("\n❌ Task could not be completed")

                

                # Show learning progress

                apps_count = len(self.utility_ai.knowledge.working_apps)

                browser_count = len(self.utility_ai.knowledge.browser_preferences)

                print(f"\n📚 Sarah now knows {apps_count} working apps and {browser_count} browsers")

                

            except KeyboardInterrupt:

                print("\n👋 Goodbye!")

                break

            except Exception as e:

                print(f"❌ System error: {e}")



def main():

    """Main entry point"""

    if not HAS_OLLAMA:

        print("❌ Ollama is required for the LLM director")

        return

    

    try:

        sarah = EnhancedExperientialSarah()

        sarah.run_interactive()

    except Exception as e:

        print(f"❌ Failed to initialize: {e}")



if __name__ == "__main__":

    main()