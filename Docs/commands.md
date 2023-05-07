g3 Commands
===========

Implemented commands
--------------------

Command specifications are listed as `.Request` in the datasheet AN5603.

 Command        | Notes
----------------|-------
 HOSTIF-DBGTOOL | Used for a couple of purposes, right now the only implementation is to get the information response.


Adding a new command
--------------------

New commands are fairly easy to implement, and the base class, `C3Cmd`, already implements most of
the necessary functionality. In short the steps are:

1. Create a new class subclassed from `G3Cmd` in file `g3_comms/g3_cmd.py`.
2. Implement metadata `g3_id`, `g3_name`, `rx_msg`. See below.
3. In the new command class, implement overides for `_add_parser()` and `encode_cmd()`.
4. Implement the override for `parse_args()`. This is almost always necessary, however, it is
optional if there are no parameters that need to be implemented.
5. Instantiate the new class in `g3_cli.py`.

### 1. Create new class

This step is simple.  Instantiate a new class from G3Cmd:

```
class NewCmd(G3Cmd):
```

### 2. Implement metadata

The metadata in the class implements the necessary data in order for the command encoding to work
as well as to link the command to any relevant responses.

#### `g3_id`

This field needs to be set to the value for the relevant command from the datasheet. It should be a
two digit hex integer.

#### `g3_name`

The name should be set to the name from the datasheet, without the suffix part (".Request"). Note
that the name on the Cmd and the Resp are used to match, so it's best to use the same value from
the datasheet (and watch the spelling).

#### `rx_msgs`

`rx_msgs` is a list of the messages that we expect to receive as a response when we send the
command. The entries must match `g3_name` from the relevant Resp class.

This list is used to setup the callbacks the class utilizes to trigger it's own callback. Right now
the only use for this is via the `send_and_wait()` to determine when we've received the expected
messages. Note that the current implementation assumes "and" logic. In other words, all of the
listed responses must be received in order to trigger the command callback.

### 3. and 4. Implement overrides

#### `def encode_cmd(self):`

`encode_cmd()` is the function that gets called to build the data packet for the command. All the
data should come from the dictionary `self.fields`. It will need to encode the data using
`struct.pack()` and then return that `Bytes` data.

`encode_cmd()` is not user-called, it is called directly by the g3_tx infrastructure code.

#### `def _add_parser(self, subparsers):`

`_add_parser()` is not user-called, it is called by the super-class's `__init__()` to create an
argparse subparser. This should use the `subparsers.add_parser()` to add the CLI for the command
and parse any CLI arguments.

#### `parse_args(self, args):`

`parse_args()`, while technically optional, almost always needs to be implmented. This function
expects to use the data in an `argparse` `args` to fill in `self.fields`.

### 5. Instantiate the new class

Finally, in `g3_cli.py` you need to instantiate an object of the new class:

```
g3_comms.g3_msgs.msg_cmds['newcmd'] = g3_cmd.NewCmd(subparsers)
```

A couple of comments about the above. We utilize the dict `g3_comms.g3_msgs.msg_cmds` to store the
objects for later use. We also pass `subparsers` which is already instantiated so that the CLI
arguments get connected properly.
