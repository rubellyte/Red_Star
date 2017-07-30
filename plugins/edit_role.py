import asyncio
from discord import InvalidArgument, Colour
from plugin_manager import BasePlugin
from utils import Command, respond, split_message

class RoleCommands(BasePlugin):
	name = "role_commands"
	
	def activate(self):
		pass
		
	@Command("editrole",
		perms={"manage_server"},
		syntax= "(role name) [name=string][colour=0xFFFFFF][hoist=true/false][mentionable=true/false]",
		doc= "Edits the specified role name, colour, hoist (show separately from others) and mentionable properties.\n"
		"WARNING: Options must be specified as option=value. No spaces around `=`.\n"
		"ANALYSIS: Colour can be reset by setting it to 0.")
	async def _editrole(self,data):
		"""
			a command for editing a role.
			!editrole (role name) [name=name][colour=colour][hoist=hoist][mentionable=mentionable]
			name is a string
			colour is a colour object (value converted from hexadecimal string)
			hoist and mentionable are boolean
		"""
		args = data.content.split()
		if len(args)>1:
			err = True
			for server in self.client.servers:
				for role in server.roles:
					if args[1].lower() == role.name.lower(): #found role
						for x in args:
							print(x)
						err = False
						t_dict = {}
						for arg in args[2:]:
							t_arg = arg.split("=")
							if len(t_arg)>1: #beautiful
								if t_arg[0].lower() == "name":
									t_dict["name"] = t_arg[1]
								elif t_arg[0].lower() == "colour":
									t_dict["colour"] = Colour(int(t_arg[1],16))
								elif t_arg[0].lower() == "hoist":
									t_dict["hoist"] = t_arg[1].lower()=="true"
								elif t_arg[0].lower() == "mentionable":
									t_dict["mentionable"] = t_arg[1].lower()=="true"
						if len(t_dict)==0:		#you're wasting my time
							raise SyntaxError
						await self.client.edit_role(server,role,**t_dict)
						t_string = ""
						for k,v in t_dict.items():
							t_string += k+": "+str(v)+"\n "
						await respond(self.client,data,"**AFFIRMATIVE. Role {} modified with parameters :**\n ```{}```".format(args[1].lower(),t_string))
						break
			if err:
				await respond(self.client, data, "**NEGATIVE. ANALYSIS: no role {}.**".format(args[1]))
		else:
			raise SyntaxError