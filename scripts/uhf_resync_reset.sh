cmc="10.103.254.3"
port=$(kcpcmd -s $cmc:7147 array-list | grep array-list | cut -f3 -d' ' | cut -f1 -d',')
echo $port
for prt in $port
do 
    inst=$(kcpcmd -t 10 -s $cmc:$prt sensor-value | grep instrument-state | cut -f6 -d' ')
    if [[ $inst = *544* ]]
    then
        kcpcmd -t 10 -s $cmc:$prt feng-auto-resync-reset
    fi
done
