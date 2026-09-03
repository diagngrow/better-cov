function declared() {
  return 1;
}

async function load() {
  return 2;
}

function* identifiers() {
  yield 3;
}

const doubled = (value) => {
  return value * 2;
};

class Worker {
  run() {
    return doubled(2);
  }

  static async build() {
    return new Worker();
  }
}

const helpers = {
  format(value) {
    return value;
  },
  normalize: function (value) {
    return value.trim();
  },
};

function inner() {
  return helpers.format(4);
}

function outer() {
  return inner();
}

const View = () => (
  <section>
    <span>content</span>
  </section>
);
