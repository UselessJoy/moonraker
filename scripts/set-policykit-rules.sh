#!/bin/bash
# This script installs Moonraker's PolicyKit Rules used to grant access

POLKIT_LEGACY_DIR="/etc/polkit-1/localauthority/50-local.d"
POLKIT_DIR="/etc/polkit-1/rules.d"
MOONRAKER_UNIT="/etc/systemd/system/moonraker.service"
MOONRAKER_GID="-1"

verify_polkit() {
    if ! command -v pkaction &> /dev/null; then
        echo "PolicyKit not installed"
        exit 1
    fi
}

check_moonraker_service()
{

    # Force Add the moonraker-admin group
    sudo groupadd -f moonraker-admin
    [ ! -f $MOONRAKER_UNIT ] && return
    # Make sure the unit file contains supplementary group
    HAS_SUPP="$( grep -cm1 "SupplementaryGroups=moonraker-admin" $MOONRAKER_UNIT || true )"
    [ "$HAS_SUPP" -eq 1 ] && return
    report_status "Adding moonraker-admin supplementary group to $MOONRAKER_UNIT"
    sudo sed -i "/^Type=simple$/a SupplementaryGroups=moonraker-admin" $MOONRAKER_UNIT
    sudo systemctl daemon-reload
}

add_polkit_legacy_rules()
{
    RULE_FILE="${POLKIT_LEGACY_DIR}/10-moonraker.pkla"
    echo "Установка legacy-правил PolicyKit в ${RULE_FILE}..."
    
    sudo mkdir -p "$POLKIT_LEGACY_DIR"
    sudo tee "$RULE_FILE" > /dev/null <<EOF
[moonraker permissions]
Identity=unix-user:$USER
Action=org.freedesktop.systemd1.manage-units;org.freedesktop.login1.power-off;org.freedesktop.login1.power-off-multiple-sessions;org.freedesktop.login1.reboot;org.freedesktop.login1.reboot-multiple-sessions;org.freedesktop.timedate1.set-time;org.freedesktop.packagekit.*
ResultAny=yes
EOF
}

add_polkit_rules()
{
    RULE_FILE="${POLKIT_DIR}/10-moonraker.rules"
    MOONRAKER_GID=$(getent group moonraker-admin | awk -F: '{printf "%d", $3}')
    sudo mkdir -p "$POLKIT_DIR"
    sudo tee "$RULE_FILE" > /dev/null <<EOF
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.systemd1.manage-units" ||
         action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
         action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
         action.id == "org.freedesktop.timedate1.set-time" ||
         action.id.startsWith("org.freedesktop.packagekit.")) &&
        subject.user == "$USER") {
        
        // Проверка принадлежности к группе moonraker-admin
        var regex = "^Groups:.+?\\\\s$MOONRAKER_GID[\\\\s\\\\0]";
        var cmdpath = "/proc/" + subject.pid.toString() + "/status";
        try {
            polkit.spawn(["grep", "-Pq", regex, cmdpath]);
            return polkit.Result.YES;
        } catch (error) {
            return polkit.Result.NOT_HANDLED;
        }
    }
});
EOF
}

add_ap_rules()
{
    RULE_FILE="${POLKIT_DIR}/5-access-point.rules"
    sudo mkdir -p "$POLKIT_DIR"
    sudo tee "$RULE_FILE" > /dev/null <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 && subject.user === "$USER") {
        return polkit.Result.YES;
    }
}); 
EOF
}

create_dispatcher_rule() {
    DISPATCHER_DIR="/etc/NetworkManager/dispatcher.d"
    DISPATCHER_RULE="${DISPATCHER_DIR}/wlan-metric"
    
    if [ ! -f "$DISPATCHER_RULE" ]; then
        echo "Создание правила NetworkManager..."
        sudo tee "$DISPATCHER_RULE" > /dev/null <<'EOF'
#!/bin/sh
if [ "$1" = "wlan0" ] && [ "$2" = "up" ]; then
    nmcli connection modify "$CONNECTION_ID" ipv4.route-metric 50
fi
EOF
        sudo chmod 755 "$DISPATCHER_RULE"
    fi
}

clear_polkit_rules() {
    echo "Удаление старых правил Moonraker..."
    sudo rm -f "${POLKIT_LEGACY_DIR}/10-moonraker.pkla"
    sudo rm -f "${POLKIT_DIR}/90-moonraker.rules"
}

verify_ready() {
    if [ "$EUID" -eq 0 ]; then
        echo "Скрипт не должен запускаться от root!"
        exit 1
    fi
}

get_polkit_version() {
    pkaction --version | awk '{print $NF}' | cut -d. -f1-2
}

# Helper functions
report_status()
{
    echo -e "\n\n###### $1"
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

CLEAR="n"
ROOT="n"
DISABLE_SYSTEMCTL="n"
verify_polkit
# Parse command line arguments
while :; do
    case $1 in
        -c|--clear)
            CLEAR="y"
            ;;
        -r|--root)
            ROOT="y"
            ;;
        -z|--disable-systemctl)
            DISABLE_SYSTEMCTL="y"
            ;;
        *)
            break
    esac

    shift
done

if [ "$ROOT" = "n" ]; then
    verify_ready
fi

if [ "$CLEAR" = "y" ]; then
    clear_polkit_rules
else
    set -e
    check_moonraker_service
    POLKIT_VERSION=$(get_polkit_version)
    if awk "BEGIN {exit !($POLKIT_VERSION < 0.106)}"; then
        add_polkit_legacy_rules
    else
        add_ap_rules
        add_polkit_rules
    fi
    create_dispatcher_rule
    if [ $DISABLE_SYSTEMCTL = "n" ]; then
        report_status "Restarting Moonraker..."
        sudo systemctl restart moonraker
    fi
fi
