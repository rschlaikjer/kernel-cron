#!/usr/bin/env python
import urllib2
import subprocess
import os
import json

KERNEL_JSON_URI = "https://www.kernel.org/releases.json"
BUILD_DIRECTORY = "/usr/src/"
DEB_DIRECTORY = "/var/www/"
REPREPO_DIRECTORY = "/var/www/debian/"
METADATA_DIRECTORY = "/home/ross/kernelbuilder/"
LOCKFILE = "/tmp/kernel-builder-lock"

DISTS = [ 'beast', 'mjolnir', 'saddle' ]

def fetch_kernel_versions():
    response = urllib2.urlopen(KERNEL_JSON_URI)
    kernel_json_s = response.read()
    kernel_json = json.loads(kernel_json_s)
    return [
            {
                "version": release["version"],
                "source":release["source"]
                }
            for release in kernel_json["releases"]
            if 'rc' not in release["version"]
            ]

def has_been_built(release, dist):
    filepath = os.path.join(
                METADATA_DIRECTORY,
                ".".join([release["version"], dist])
                )
    return os.path.exists(filepath)

def get_attempt_filepath(release, dist):
    return os.path.join(
        METADATA_DIRECTORY,
        ".".join([release["version"], dist, "attempt"])
    )

def record_attempt(release, dist):
    subprocess.call([
        'touch',
        get_attempt_filepath(release, dist)
    ])

def has_been_attempted(release, dist):
    return os.path.exists(get_attempt_filepath(release, dist))

def parse_version(release):
    major_offset = release["version"].index(".")
    minor_offset = 0
    try:
        minor_offset = release["version"].index(".", major_offset+1)
    except ValueError:
        minor_offset= len(release["version"])
    major = release["version"][:major_offset]
    minor = release["version"][major_offset+1:minor_offset]
    return "{major}.{minor}".format(major=major, minor=minor)

def build_kernel(release, dist):
    try:
        kernel_config_ver = parse_version(release)
    except ValueError:
        raise Exception("Failed to parse config ver for {0}".format(release["version"]))

    config_filepath = os.path.join(
            METADATA_DIRECTORY,
            "config.{d}.{v}".format(
                d=dist,
                v=kernel_config_ver,
            ))
    if not os.path.exists(config_filepath):
        raise Exception("Missing kernel config for series {s}".format(s=kernel_config_ver))

    kernel_source_tar = os.path.join(
            BUILD_DIRECTORY,
            'linux-{v}.tar.xz'.format(v=release["version"])
            )
    subprocess.Popen([
        'wget',
        '-nc',
        release["source"],
        '-O',
        kernel_source_tar
        ]).communicate()

    subprocess.Popen([
        'tar',
        'xvf',
        kernel_source_tar,
        ],
        cwd=BUILD_DIRECTORY
        ).communicate()

    subprocess.call([
        'rm',
        '-f',
        kernel_source_tar
        ])

    kernel_builddir = os.path.join(
            BUILD_DIRECTORY,
            'linux-{v}'.format(v=release["version"])
            )

    subprocess.call([
        'cp',
        config_filepath,
        os.path.join(
            kernel_builddir,
            ".config"
            )
        ])


    print "Building {release} for dist {dist} using config for series {config}".format(
        release=release["version"],
        config=kernel_config_ver,
        dist=dist,
    )
    subprocess.call(
        'yes "" | make oldconfig',
        cwd=kernel_builddir,
        shell=True
    )

    subprocess.Popen([
        'bash',
        './scripts/config',
        '--set-str',
        'CONFIG_LOCALVERSION',
        '-{dist}'.format(dist=dist),
        ],
        cwd=kernel_builddir
        ).communicate()

    subprocess.Popen([
        'make',
        '-j8',
        'deb-pkg',
        'CONFIG_LOCALVERSION=-{dist}'.format(dist=dist),
        ],
        cwd=kernel_builddir
        ).communicate()


    files_in_src = [
            f for f in os.listdir(BUILD_DIRECTORY)
            if os.path.isfile(os.path.join(BUILD_DIRECTORY, f))
            ]

    debs = [ f for f in files_in_src if f.endswith(".deb")]

    kernel_deb_path = os.path.join(DEB_DIRECTORY, release["version"])
    subprocess.call([
        'mkdir',
        '-p',
        kernel_deb_path
        ])

    for deb in debs:
        subprocess.call([
            'mv',
            os.path.join(BUILD_DIRECTORY, deb),
            kernel_deb_path
            ])

        #Add the deb to the repo
        subprocess.call([
            'reprepro',
            'includedeb',
            'testing',
            os.path.join(kernel_deb_path, deb),
            ],
            cwd=REPREPO_DIRECTORY
            )

    subprocess.call([
        'cp',
        os.path.join(kernel_builddir, '.config'),
        os.path.join(kernel_deb_path, 'config')
        ])

    subprocess.call([
        'touch',
        os.path.join(
            METADATA_DIRECTORY,
            ".".join([release["version"], dist]),
        )
        ])


    subprocess.call([
        'rm',
        '-fr',
        kernel_builddir
        ])

    kernel_prefix = 'linux-{version}-{dist}'.format(
        version=release["version"],
        dist=dist
    )
    files_to_clean = [ f for f in files_in_src if f.startswith(kernel_prefix) ]
    for f in files_to_clean:
        subprocess.call([
            'rm',
            '-f',
            os.path.join(BUILD_DIRECTORY, f)
        ])

    return

def generate_metapackage(release, dist):
    ns_control = """Section: misc
Priority: optional
Homepage: https://kernels.rhye.org/
Standards-Version: 3.9.2

Package: linux-{dtype}-{dist}
Version: {release}
Maintainer: Ross Schlaikjer <ross@schlaikjer.net>
Depends: linux-{dtype}-{release}-{dist}
Architecture: amd64
Description: Metapackage for {dist}'s autogenerated kernels
 This package depends on the most recent version of the kernels autogenerated by
 the Rhye build system, targeted at my laptop.
"""

    # If the release has no minor number, assume it's a zero
    verstring = release["version"]
    if verstring.find(".", 2) == -1:
        verstring = "{0}.0".format(verstring)

    for debtype in ["image", "headers"]:
        control_dir = os.path.join(
            METADATA_DIRECTORY,
            "linux-{dtype}-{dist}".format(dtype=debtype, dist=dist)
        )
        control_file = os.path.join(control_dir, "ns-control")
        try:
            os.makedirs(control_dir)
        except Exception:
            pass
        try:
            with open(control_file, 'w') as outfile:
                outfile.write(ns_control.format(
                    release=verstring,
                    dtype=debtype,
                    dist=dist,
                ))
            subprocess.call([
                'equivs-build',
                'ns-control'
            ], cwd=control_dir)

        except Exception, e:
            print e

        files_in_src = [
                f for f in os.listdir(control_dir)
                if os.path.isfile(os.path.join(control_dir, f))
                ]

        debs = [ f for f in files_in_src if f.endswith(".deb")]

        kernel_deb_path = os.path.join(DEB_DIRECTORY, release["version"])
        subprocess.call([
            'mkdir',
            '-p',
            kernel_deb_path
            ])

        for deb in debs:
            subprocess.call([
                'mv',
                os.path.join(control_dir, deb),
                kernel_deb_path
                ])

            #Add the deb to the repo
            subprocess.call([
                'reprepro',
                'includedeb',
                'testing',
                os.path.join(kernel_deb_path, deb),
                ],
                cwd=REPREPO_DIRECTORY
                )

        # Export the repo
        subprocess.call([
            'reprepro',
            'export',
            'testing',
            ],
            cwd=REPREPO_DIRECTORY
            )


def notify_failed(release, dist, e):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(e.message)
    msg['Subject'] = 'Failed to build kernel {0} for dist {1}'.format(
        release['version'],
        dist,
    )

    msg['From'] = 'ross@vbuild'
    msg['To'] = 'ross@xvjpf.org'
    s = smtplib.SMTP('localhost')
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()

def notify_built(release, dist):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText("http://kernels.rhye.org/{0}".format(release['version']))
    msg['Subject'] = 'Built kernel {0} for dist {1}'.format(
        release['version'],
        dist,
    )
    msg['From'] = 'ross@vbuild'
    msg['To'] = 'ross@xvjpf.org'
    s = smtplib.SMTP('localhost')
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()

def main():
    if os.path.isfile(LOCKFILE):
        return
    open(LOCKFILE, 'a').close()

    kernel_vers = [
            version for version in fetch_kernel_versions()
            if not version['version'].startswith("next")
            ]
    for dist in DISTS:
        for version in kernel_vers:
            if (not has_been_built(version, dist)
                and not has_been_attempted(version, dist)):
                try:
                    record_attempt(version, dist)
                    build_kernel(version, dist)
                    notify_built(version, dist)
                    generate_metapackage(version, dist)
                except Exception, e:
                    notify_failed(version, dist, e)
    os.remove(LOCKFILE)

main()
