package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp18 city-capacity: reject creating an owner when the owner's city already contains 50+
 *  owners (409). Fill a fresh, unique city to exactly 50, then the 51st in that city is rejected. */
@Tag("cp18")
class Cp18Tests extends AcceptanceBase {

	@Test
	void coreRejectsWhenCityAtCapacity() throws Exception {
		String city = "Cap" + seq();
		fillCity(city, 50);
		ObjectNode o = ownerNode();
		o.put("city", city);
		createOwner(o).andExpect(status().isConflict());
	}
}
