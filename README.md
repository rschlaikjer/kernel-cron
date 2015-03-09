#Kernel-Cron

This is a pretty simple script I put together to automatically check kernel.org
for new releases, build them and then put them into an APT repository so that I
can have my devices automatically pull the latest kernels.

Custom configs can be specified for each kernel version. There are also email
notifications when a build is done.

I have a VM building these kernels and putting them up
[here](http://kernels.rhye.org/), which can be added as an apt repo by:

    echo 'deb http://kernels.rhye.org/debian/ testing main' | sudo tee /etc/apt/sources.list.d/vbuild.list
    wget -O - http://kernels.rhye.org/debian/vbuild.gpg.key | sudo apt-key add -


