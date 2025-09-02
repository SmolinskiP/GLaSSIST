# 🎯 GLaSSIST Interactive Prompts - Complete Setup Guide

Transform your Home Assistant into a truly conversational smart home! GLaSSIST can now receive prompts from HA, ask questions via TTS, listen for voice responses, and execute actions based on what you say.

## 🚀 How It Works

**The Magic Flow:**
1. 🏠 **HA detects event** (door opens, motion detected, etc.)
2. 🔗 **HA sends HTTP request** to GLaSSIST with question + AI context instructions
3. 🎤 **GLaSSIST asks user** the question via TTS 
4. 🗣️ **User responds** with voice
5. 🧠 **GLaSSIST sends to HA AI** user response + context instructions
6. ✅ **HA AI understands context** and executes appropriate action

**Example:**
> Door opens → HA sends: *"Welcome home! Want lights and coffee?" + context: "User arriving home, activate arrival routine if they agree"* → GLaSSIST asks → You: *"Yes please!"* → GLaSSIST sends: *"Context: User arriving home, activate arrival routine if they agree. User said: Yes please"* → HA AI turns on lights and starts coffee

## 🏠 Home Assistant Configuration

### Step 1: Add REST Command

Add this to your `configuration.yaml`:

```yaml
rest_command:
  glassist_prompt:
    url: "http://192.168.1.100:8766/prompt"  # Change IP to your GLaSSIST machine
    method: POST
    headers:
      Content-Type: "application/json"
    payload: |
      {
        "message": "{{ message }}",
        "context": "{{ context }}",
        "timeout": {{ timeout | default(15) }},
        "wait_for_response": {{ wait_for_response | default(true) | lower }}
      }
```

### Parameters

- **message**: The text GLaSSIST should speak
- **context**: Context information for the conversation (optional)  
- **timeout**: How long to wait for user response in seconds (default: 15)
- **wait_for_response**: Whether to wait for user input after TTS (default: true)
  - `true`: Normal interactive mode - plays TTS then waits for voice response
  - `false`: TTS-only mode - plays TTS then ends (for announcements)

### Step 2: Epic Automation Examples

#### 🌅 Smart Morning Routine
```yaml
automation:
  - alias: "🌅 Smart Morning Greeting"
    description: "Personalized morning routine with weather and coffee"
    trigger:
      - platform: state
        entity_id: binary_sensor.bedroom_motion
        to: 'on'
    condition:
      - condition: time
        after: "06:00:00"
        before: "10:00:00"
      - condition: state
        entity_id: input_boolean.morning_routine_done
        state: 'off'
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            Good morning! It's {{ states('sensor.temperature_outside') }}°C outside with {{ states('weather.home') }}.
            Should I start your morning routine? Coffee, news briefing, and optimal lighting?
          context: "User is waking up in the morning. If they agree, activate morning routine: turn on coffee maker, start news briefing, and set optimal lighting"
          timeout: 20
```

#### 🚪 Intelligent Door Entry
```yaml
  - alias: "🚪 Smart Welcome Home"
    description: "Context-aware arrival with personalized greeting"
    trigger:
      - platform: state
        entity_id: lock.front_door
        to: 'unlocked'
    condition:
      - condition: state
        entity_id: person.john
        state: 'home'
        for: "00:00:30"
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            {% set time_away = (now() - states.person.john.last_changed).total_seconds() / 3600 %}
            {% if time_away > 8 %}
            Welcome back! You've been away for {{ time_away | round(1) }} hours.
            Shall I activate arrival mode? Lights on, climate to comfort, and check what happened while you were gone?
            {% else %}
            Quick trip! Want me to resume where we left off?
            {% endif %}
          context: "User just arrived home after being away. If they want arrival mode, turn on lights, set comfortable temperature, and provide status update of what happened while away"
          timeout: 25
```

#### 🎬 Cinematic Experience
```yaml
  - alias: "🎬 Movie Night Magic"
    description: "Automatic movie mode activation with ambient setup"
    trigger:
      - platform: state
        entity_id: media_player.living_room_tv
        to: 'playing'
    condition:
      - condition: time
        after: "18:00:00"
      - condition: state
        entity_id: media_player.living_room_tv
        attribute: media_content_type
        state: 'movie'
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            I see you're watching "{{ state_attr('media_player.living_room_tv', 'media_title') }}".
            Activate cinema mode? I'll dim the lights, close blinds, and enable do-not-disturb.
          context: "User is watching a movie. If they want cinema mode, dim the lights, close blinds, and enable do-not-disturb mode"
          timeout: 15
```

#### 🛡️ Security & Departure
```yaml
  - alias: "🛡️ Intelligent Departure"
    description: "Smart home security with contextual actions"
    trigger:
      - platform: state
        entity_id: person.john
        from: 'home'
        to: 'away'
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            {% set lights_on = states.light | selectattr('state', 'equalto', 'on') | list | count %}
            {% set devices_on = states.switch | selectattr('state', 'equalto', 'on') | list | count %}
            You're leaving home. I found {{ lights_on }} lights and {{ devices_on }} devices still on.
            Activate secure departure mode? I'll turn off everything, arm security, and set climate to away.
          context: "User is leaving home. If they want secure departure mode, turn off all lights and devices, arm security system, and set climate to away mode"  
          timeout: 30
```

#### 🌙 Bedtime Intelligence
```yaml
  - alias: "🌙 Smart Bedtime Routine"
    description: "Contextual bedtime with tomorrow preparation"
    trigger:
      - platform: state
        entity_id: binary_sensor.bedroom_motion
        to: 'on'
    condition:
      - condition: time
        after: "21:00:00"
        before: "02:00:00"
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            {% set tomorrow_weather = state_attr('weather.home', 'forecast')[0] %}
            Time for bed! Tomorrow will be {{ tomorrow_weather.condition }} with {{ tomorrow_weather.temperature }}°C.
            Shall I prepare your bedtime routine? Dim lights, lock doors, set morning alarm,
            and adjust climate for optimal sleep?
          context: "User is going to bed. If they want bedtime routine, dim lights, lock doors, set morning alarm, and adjust climate for optimal sleep"
          timeout: 20
```

#### ⚡ Energy Management
```yaml
  - alias: "⚡ Smart Energy Alert"
    description: "Intelligent power usage optimization"
    trigger:
      - platform: numeric_state
        entity_id: sensor.current_power_usage
        above: 3000
        for: "00:05:00"
    action:
      - service: rest_command.glassist_prompt
        data:
          message: >
            High energy usage detected! Currently consuming {{ states('sensor.current_power_usage') }}W.
            The main culprits are heating and entertainment system.
            Should I optimize power usage by adjusting climate and non-essential devices?
          context: "High energy usage detected. If user agrees to optimize, reduce climate temperature by 2°C, turn off non-essential devices and lights to save power"
          timeout: 18
```

### Step 3: How AI Processes Responses

When user responds, GLaSSIST sends to HA AI:
*"Context: [your context instructions]. User said: [user voice response]"*

The AI automatically understands what to do based on context and executes appropriate actions. No additional scripts needed - HA AI handles everything!

**Example:**
- GLaSSIST sends: *"Context: User is leaving home. If they want secure departure mode, turn off all lights. User said: Yes please"*
- HA AI automatically turns off lights, arms security, etc.


## 🧠 How Context Works in Practice

**The AI automatically understands context!** No complex configuration needed.

**Examples of what GLaSSIST sends to HA AI:**

1. **Morning Routine:**
   - *"Context: User is waking up in the morning. If they agree, activate morning routine: turn on coffee maker, start news briefing, and set optimal lighting. User said: Yes please"*
   - HA AI → Turns on coffee, starts news, optimizes lighting

2. **Energy Optimization:**
   - *"Context: High energy usage detected. If user agrees to optimize, reduce climate temperature by 2°C, turn off non-essential devices. User said: Do it"*
   - HA AI → Reduces temperature, turns off gaming PC and entertainment center

3. **Departure Security:**
   - *"Context: User is leaving home. If they want secure departure mode, turn off all lights and devices, arm security system. User said: Secure everything"*
   - HA AI → Executes full departure sequence

**The beauty:** HA AI understands natural language context instructions and user responses automatically!

## 🧪 Testing Your Setup

### Quick API Test
```bash
# Test if GLaSSIST is listening
curl -X POST http://192.168.1.100:8766/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "message": "This is a test. Are you ready for some awesome home automation?",
    "context": "This is a connection test. If user responds positively, confirm the system is working properly",
    "timeout": 15
  }'
```

### HA Developer Tools Test
Go to `Developer Tools > Services`:

**Service:** `rest_command.glassist_prompt`

**Data:**
```yaml
message: "Testing the connection. Can you hear me and respond with your voice?"
context: "This is a connection test. If user responds, confirm that GLaSSIST and Home Assistant are communicating properly"
timeout: 20
```




Ready to make your home truly intelligent and conversational? Your smart home just got a voice and personality! 🎉
