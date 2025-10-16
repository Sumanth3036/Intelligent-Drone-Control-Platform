# Makefile for Webots robot_window plugin

# Webots installation directory (adjust if needed)
WEBOTS_HOME ?= C:/Program Files/Webots

# Include and library paths
INCLUDE = -I"$(WEBOTS_HOME)/include"
LIB = -L"$(WEBOTS_HOME)/lib/controller" -lcontroller

# Compiler settings
CC = gcc
CFLAGS = -Wall -O2 $(INCLUDE) -DWEBOTS_ROBOT_WINDOW
LDFLAGS = $(LIB) -shared

# Source and output files
SOURCES = orientation_display.c
TARGET = orientation_display.dll

# Default target
all: $(TARGET)

# Build the DLL
$(TARGET): $(SOURCES)
	@echo "Building robot window plugin..."
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
	@echo "✓ Plugin built successfully: $(TARGET)"

# Clean target
clean:
	@echo "Cleaning build files..."
	rm -f $(TARGET)
	@echo "✓ Clean completed"

# Install target (copy to Webots plugins directory)
install: $(TARGET)
	@echo "Installing plugin to Webots..."
	copy "$(TARGET)" "$(WEBOTS_HOME)\projects\plugins\robot_windows\"
	@echo "✓ Plugin installed"

# Help target
help:
	@echo "Available targets:"
	@echo "  all     - Build the plugin (default)"
	@echo "  clean   - Remove build files"
	@echo "  install - Copy plugin to Webots directory"
	@echo "  help    - Show this help"

.PHONY: all clean install help