// Contact-gated idealized suction. No force/slip/seal model is implied.
#include <atomic>
#include <sstream>
#include <ignition/gazebo/System.hh>
#include <ignition/gazebo/Model.hh>
#include <ignition/gazebo/Util.hh>
#include <ignition/gazebo/components/ContactSensorData.hh>
#include <ignition/gazebo/components/Collision.hh>
#include <ignition/gazebo/components/DetachableJoint.hh>
#include <ignition/gazebo/components/Name.hh>
#include <ignition/gazebo/components/ParentEntity.hh>
#include <ignition/gazebo/components/Model.hh>
#include <ignition/plugin/Register.hh>
#include <ignition/transport/Node.hh>
#include <ignition/msgs/boolean.pb.h>
#include <ignition/msgs/stringmsg.pb.h>

namespace robotlab {
namespace sim = ignition::gazebo;
namespace comp = sim::components;
class ContactGripper : public sim::System, public sim::ISystemConfigure,
                       public sim::ISystemPreUpdate {
 public:
  void Configure(const sim::Entity &entity, const std::shared_ptr<const sdf::Element> &sdf,
                 sim::EntityComponentManager &ecm, sim::EventManager &) override {
    parent = sim::Model(entity).LinkByName(ecm, sdf->Get<std::string>("parent_link"));
    childName = sdf->Get<std::string>("child_model");
    childLinkName = sdf->Get<std::string>("child_link");
    node.Subscribe("/robotlab/gripper/enable", &ContactGripper::Enable, this);
    publisher = node.Advertise<ignition::msgs::StringMsg>("/robotlab/gripper/state");
  }
  void Enable(const ignition::msgs::Boolean &msg) { enabled.store(msg.data()); }
  void PreUpdate(const sim::UpdateInfo &info, sim::EntityComponentManager &ecm) override {
    if (info.paused || parent == sim::kNullEntity) return;
    // Enable physics contact reporting on the actual cup collisions. URDF
    // conversion may rename them when fixed links are lumped.
    ecm.Each<comp::Collision, comp::ParentEntity>(
      [&](const sim::Entity &entity, const comp::Collision *, const comp::ParentEntity *owner) {
        if (owner->Data() == parent && !ecm.Component<comp::ContactSensorData>(entity))
          ecm.CreateComponent(entity, comp::ContactSensorData());
        return true;
      });
    if (child == sim::kNullEntity) {
      auto model = ecm.EntityByComponents(comp::Model(), comp::Name(childName));
      if (model != sim::kNullEntity) child = sim::Model(model).LinkByName(ecm, childLinkName);
    }
    bool contact = false;
    int pairs = 0;
    ecm.Each<comp::ContactSensorData, comp::Name, comp::ParentEntity>(
      [&](const sim::Entity &, const comp::ContactSensorData *data,
          const comp::Name *name, const comp::ParentEntity *owner) {
        if (owner->Data() != parent) return true;
        for (const auto &pair : data->Data().contact()) {
          ++pairs;
          auto first = ecm.Component<comp::ParentEntity>(pair.collision1().id());
          auto second = ecm.Component<comp::ParentEntity>(pair.collision2().id());
          if (first && second && ((first->Data() == parent && second->Data() == child) ||
                                  (second->Data() == parent && first->Data() == child))) contact = true;
        }
        return true;
      });
    if (!enabled.load()) {
      contactSteps = 0;
      if (joint != sim::kNullEntity) {
        ecm.RequestRemoveEntity(joint);
        joint = sim::kNullEntity;
      }
    } else if (joint == sim::kNullEntity && child != sim::kNullEntity) {
      contactSteps = contact ? contactSteps + 1 : 0;
      if (contactSteps >= 3) {
        contactsAtAttach = contactSteps;
        joint = ecm.CreateEntity();
        ecm.CreateComponent(joint, comp::DetachableJoint({parent, child, "fixed"}));
      }
    }
    if (info.simTime - lastReport >= std::chrono::milliseconds(100)) {
      lastReport = info.simTime;
      std::ostringstream text;
      text << "{\"attached\":" << (joint != sim::kNullEntity ? "true" : "false")
           << ",\"contact\":" << (contact ? "true" : "false")
           << ",\"contact_pairs\":" << pairs
           << ",\"contact_steps_at_attach\":" << contactsAtAttach;
      if (child != sim::kNullEntity) {
        auto pose = sim::worldPose(child, ecm);
        text << ",\"token_xyz\":[" << pose.Pos().X() << "," << pose.Pos().Y()
             << "," << pose.Pos().Z() << "]";
      }
      text << "}";
      ignition::msgs::StringMsg msg;
      msg.set_data(text.str());
      publisher.Publish(msg);
    }
  }
 private:
  sim::Entity parent{sim::kNullEntity}, child{sim::kNullEntity}, joint{sim::kNullEntity};
  std::string childName, childLinkName;
  std::atomic<bool> enabled{false};
  int contactSteps{0}, contactsAtAttach{0};
  std::chrono::steady_clock::duration lastReport{0};
  ignition::transport::Node node;
  ignition::transport::Node::Publisher publisher;
};
}
IGNITION_ADD_PLUGIN(robotlab::ContactGripper, ignition::gazebo::System,
    robotlab::ContactGripper::ISystemConfigure, robotlab::ContactGripper::ISystemPreUpdate)
