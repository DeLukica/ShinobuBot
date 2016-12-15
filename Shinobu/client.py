
import discord
from importlib import reload as reloadmod
import sys
import asyncio
import json
from Shinobu.utility import ConfigManager

class Shinobu(discord.Client):
    def __init__(self, config_directory:str):
        super(Shinobu,self).__init__()
        self.command_list = []
        self.idle = False
        self.loop = asyncio.get_event_loop()
        self.config_directory = config_directory
        self.loaded_modules = []
        self.propagate = True
        self.config = ConfigManager(config_directory + "shinobu_config.json")
        self.log = lambda x,y: print(x,y)
        sys.path.append("./modules")


    def get_command(self, command):
        for com in self.command_list:
            if com["command"] == command:
                return com
        return None

    def can_exec(self, message:discord.Message, command:dict):
        user = message.author
        if "blacklist" in command:
            if message.channel.name in command['blacklist']:
                return False, "That command cannot be used in this channel."

        if "whitelist" in command:
            if message.channel.name not in command['whitelist']:
                return False, "That command cannot be used in this channel."

        if "permissions" in command:
            for role in message.author.roles:
                if role.name in command['permissions']:
                    return True, ""
            return False, "You do not have permissions to use that command."
        return True, ""

    def exec(self, command, message:discord.Message):
        for com in self.command_list:
            if com['command'] == command:
                do_exec, reason = self.can_exec(message, com)
                if do_exec:
                    arguments = " ".join(message.content.rsplit(" ")[1:])
                    self.invoke(com['function'](message, arguments))
                else:
                    self.invoke(self.send_message(message.channel, reason))
                return

    def reload_module(self, module_name:str):
        try:
            mod = None
            for module in self.loaded_modules:
                if module.__name__ == module_name:
                    module = reloadmod(module)
                    mod = module
                    for command in self.command_list:
                        if command['module'] == module_name:
                            self.command_list.remove(command)
            if not mod:
                mod = __import__(module_name)
                mod = reloadmod(mod)
                self.loaded_modules.append(mod)
            print("{0}, Version {1}".format(mod.__name__, mod.version))
            mod.accept_shinobu_instance(self)
            if hasattr(mod, "register_commands"):
                mod.register_commands(self.Command)
            return True
        except ImportError as e:
            print(str(e))
            return False

    def Command(self, description:str, **kwargs):
        def register_command(command_function):
            command = {
                "command":command_function.__name__,
                "function":command_function,
                "module":command_function.__module__,
                "description":description
            }
            for arg in kwargs:
                command[arg] = kwargs[arg]
            self.command_list.append(command)
            return command_function
        return register_command

    def load_safemode_mods(self):
        self.loaded_modules = []
        self.command_list = []
        for modname in self.config["safemode"]:
            self.reload_module(modname)
        return len(self.loaded_modules)

    def load_all(self):
        print("####  Loading Config  ####")
        print("Attempting to load [{0}] modules".format(len(self.config["modules"])))
        self.command_list = []
        while len(self.loaded_modules) > 0:
            module = self.loaded_modules[0]
            print("Unloading {}".format(module.__name__))
            self.unload_module(module.__name__)
        # self.loaded_modules = []
        for module in self.config["modules"]:
            self.reload_module(module)
        print("##########################\n")
        return len(self.loaded_modules)


    def author_is_owner(self, message):
        return message.author.id == self.config["owner"]

    def write_config(self):
        self.config.save()

    def unload_module(self, module_name):
        for module in self.loaded_modules:
            if module.__name__ == module_name:
                if hasattr(module, "cleanup"):
                    module.cleanup()
                self.loaded_modules.remove(module)

                return True
        return False

    def quick_send(self, channel:discord.Channel, message):
        print("Quick sending: [{0}] {1}".format(channel.name, message))
        asyncio.ensure_future(self.send_message(channel, message), loop=self.loop)

    def invoke(self, coroutine:asyncio.futures.Future):
        return asyncio.ensure_future(coroutine, loop=self.loop)

    def stop_propagation(self, name):
        raise StopPropagationException(name)





class StopPropagationException(Exception):
    pass