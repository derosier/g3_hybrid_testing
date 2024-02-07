UNAME_S := $(shell uname -s)

demo_flow.png: demo_flow.msc
	mscgen -T png -i $?
ifeq ($(UNAME_S),Darwin)
	open $@
endif
