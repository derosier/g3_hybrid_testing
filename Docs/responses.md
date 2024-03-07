g3 Responses
============

Implemented responses
--------------------

Command specifications are listed as `.Request` in the datasheet AN5603.

 Command        | Notes
----------------|-------
 HOSTIF-HWRESET | Emitted when the board does a HW reset, including at power-on.
 HOSTIF-DBGTOOL | Board status information.


Adding a new response decoder
-----------------------------

New responses are fairly easy to implement, and the base class, `G3Resp`, already implements most of
the necessary functionality. In short the steps are:

1. Create a new class subclassed from `G3Resp` in file `g3_comms/g3_resp.py`.
2. Implement metadata `g3_id`, and `g3_name`.
3. In the new command class, implement overide for `decode()`.
4. Optionally implement the override for `pr_decode()`.
5. Instantiate the new class in `g3_cli.py`.

### 1. Create new class

This step is simple.  Instantiate a new class from G3Cmd:

```
class NewResp(G3Resp):
```

### 2. Implement metadata

The metadata in the class implements the necessary data in order for the command encoding to work
as well as to link the command to any relevant responses.

#### `g3_id`

This field needs to be set to the value for the relevant response from the datasheet (AN5603). It should be a
two digit hex integer. Note that the value for the command and the response are not the same number,
the response is usually +1.

The id is used to automatically run the relevant parser when the message is received.

#### `g3_name`

The name should be set to the name from the datasheet (AN5603), without the suffix part (".Confirm"). Note
that the name on the Cmd and the Resp are used to match, so it's best to use the same value from
the datasheet (AN5603) (and watch the spelling).

### 3. and 4. Implement overrides

#### `def decode(self, msg):`

`decode()` is the function that gets called to parse the binary data received from the serial port.
It should use `struct.unpack_from()` to decode the **respons's data** into self.fields. Typically
the implementation will use `unpack_from()` to put it in the list `self.raw_fields`, and then
decode that data into more "user friendly" values in `self.fields`.

The decoder is used to unpack only the data portion of the packet. The sync, header, and check
portions of the packet are handled by the calling Rx code.

`decode()` is not user-called, it is called directly by the g3_rx infrastructure code.

#### `def pr_decode(self):`

`pr_decode()` is used to print the decoded `fields` in a user-consumable way. The default
implementation can be used and prints it via the logging module with a DEBUG priority. If you want
to implement a command that actually prints out the received data, override this function and
format it how you desire.

Overriding `pr_decode()` is optional.

### 5. Instantiate the new class

Finally, in `g3_cli.py` you need to instantiate an object of the new class:

```
# Instantiate a global instance of every response we want to process on Rx
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.HWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.DBGToolResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.NewResp())
```

We utilize the list `g3_comms.g3_msgs.msg_decode_list` to store the objects for later use. The new
object must be appended to this list.
