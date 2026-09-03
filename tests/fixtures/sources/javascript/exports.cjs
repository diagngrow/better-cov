const local = () => 1;
function helper() {
  return local();
}
export { local as publicName, helper };
export default local;
module.exports = { helper, renamed: local, generated: () => 2 };
exports.direct = helper;
module.exports.alias = local;
